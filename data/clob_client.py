"""
CLOB Client — Simplified for Weather Bot.
Handles order placement on Polymarket (GTC limit orders).
Reused patterns from polymarket-bot-v2.
"""

import math
import time
import base64
import requests
from typing import Dict, Optional, Any

from config import Config
from logger import log


def _fix_base64_padding():
    """Monkey-patch py-clob-client-v2 HMAC to handle missing base64 padding."""
    try:
        import py_clob_client_v2.signing.hmac as hmac_module
        _original_b64decode = base64.b64decode

        def _safe_b64decode(s, *args, **kwargs):
            if isinstance(s, str):
                s += '=' * (-len(s) % 4)
            elif isinstance(s, bytes):
                s += b'=' * (-len(s) % 4)
            return _original_b64decode(s, *args, **kwargs)

        if hasattr(hmac_module, 'base64'):
            hmac_module.base64.b64decode = _safe_b64decode
    except Exception:
        pass

_fix_base64_padding()


class ClobClient:
    """Polymarket CLOB client for weather bot."""

    def __init__(self):
        self.base_url = Config.get_clob_url()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': f'WeatherSniper/{Config.VERSION}',
            'Accept': 'application/json',
        })
        self._py_clob_client = None
        self._wallet_address = ''

    def init_py_clob_client(self, private_key: str, funder: str = None,
                            signature_type: int = 3) -> Any:
        """Initialize CLOB V2 client with auth."""
        pk = private_key.strip()
        if not pk.startswith('0x'):
            pk = '0x' + pk

        try:
            from eth_account import Account
            self._wallet_address = Account.from_key(pk).address
        except Exception:
            pass

        from py_clob_client_v2 import ClobClient as PyClobV2
        from py_clob_client_v2.clob_types import ApiCreds

        client = PyClobV2(
            host=self.base_url,
            chain_id=Config.POLY_CHAIN_ID,
            key=pk,
            signature_type=signature_type,
            funder=funder,
        )

        # Auth flow
        api_key_obj = None
        if Config.POLY_API_KEY and Config.POLY_API_SECRET and Config.POLY_PASSPHRASE:
            api_secret = Config.POLY_API_SECRET.strip()
            api_secret += '=' * (-len(api_secret) % 4)
            api_key_obj = ApiCreds(
                api_key=Config.POLY_API_KEY.strip(),
                api_secret=api_secret,
                api_passphrase=Config.POLY_PASSPHRASE.strip(),
            )
            log.info("Using manual API creds from .env")
        else:
            try:
                api_key_obj = client.derive_api_key()
                log.info("Derived API key successfully")
            except Exception:
                try:
                    api_key_obj = client.create_or_derive_api_key()
                    log.info("Created/derived API key")
                except Exception as e:
                    raise RuntimeError(f"CLOB auth failed: {e}")

        client.set_api_creds(api_key_obj)
        self._py_clob_client = client
        log.info(f"CLOB ready — wallet: {self._wallet_address[:8]}...")
        return client


    def get_price(self, token_id: str) -> Optional[float]:
        """Get current price for a token."""
        try:
            resp = self.session.get(f"{self.base_url}/price",
                                    params={'token_id': token_id, 'side': 'BUY'}, timeout=5)
            if resp.status_code == 200:
                return float(resp.json().get('price', 0))
        except Exception:
            pass
        return None

    def get_orderbook(self, token_id: str) -> Optional[Dict]:
        """Get orderbook for a token."""
        try:
            resp = self.session.get(f"{self.base_url}/book",
                                    params={'token_id': token_id}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                bids = sorted([(float(b['price']), float(b['size'])) for b in data.get('bids', [])],
                              key=lambda x: x[0], reverse=True)
                asks = sorted([(float(a['price']), float(a['size'])) for a in data.get('asks', [])],
                              key=lambda x: x[0])
                return {
                    'bids': bids, 'asks': asks,
                    'best_bid': bids[0][0] if bids else 0.0,
                    'best_ask': asks[0][0] if asks else 1.0,
                }
        except Exception:
            pass
        return None

    def place_limit_order(self, token_id: str, side: str, price: float,
                          size_pusd: float, expiration: str = "GTC",
                          neg_risk: bool = False) -> Optional[Dict]:
        """Place a GTC limit order."""
        if not self._py_clob_client:
            log.error("CLOB client not initialized")
            return None

        try:
            from py_clob_client_v2.clob_types import OrderArgs, OrderType
            price_r = round(min(0.99, max(0.01, price)), 2)
            shares = size_pusd / price_r
            shares = max(5, math.floor(shares))  # GTC min 5 shares

            order_args = OrderArgs(
                token_id=token_id,
                price=price_r,
                size=shares,
                side=side.upper(),
            )

            if expiration.upper() == 'GTC':
                order_type = OrderType.GTC
            else:
                order_type = OrderType.FOK

            signed = self._py_clob_client.create_and_post_order(order_args)
            log.info(f"Order placed: {side} {shares} shares @ ${price_r:.2f}")
            return signed

        except Exception as e:
            log.error(f"Order failed: {e}")
            return None

    def get_pusd_balance_onchain(self, wallet_address: str) -> Optional[float]:
        """Read pUSD balance from Polygon RPC."""
        if not wallet_address:
            return None
        try:
            from web3 import Web3
            rpcs = ['https://polygon-bor-rpc.publicnode.com',
                    'https://rpc.ankr.com/polygon']
            if Config.POLYGON_RPC_URL:
                rpcs.insert(0, Config.POLYGON_RPC_URL)

            erc20_abi = [{"constant": True, "inputs": [{"name": "_owner", "type": "address"}],
                          "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}],
                          "type": "function"}]

            pusd = '0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB'
            for rpc in rpcs:
                try:
                    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={'timeout': 3}))
                    if not w3.is_connected():
                        continue
                    contract = w3.eth.contract(
                        address=Web3.to_checksum_address(pusd), abi=erc20_abi)
                    raw = contract.functions.balanceOf(
                        Web3.to_checksum_address(wallet_address)).call()
                    return raw / 1e6
                except Exception:
                    continue
        except ImportError:
            pass
        return None

    @classmethod
    def derive_wallet_address(cls) -> str:
        """Derive wallet address from private key."""
        pk = Config.POLY_PRIVATE_KEY.strip()
        if not pk:
            return ''
        try:
            from eth_account import Account
            if not pk.startswith('0x'):
                pk = '0x' + pk
            return Account.from_key(pk).address
        except Exception:
            return ''
