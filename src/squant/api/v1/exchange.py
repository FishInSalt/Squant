"""Exchange API endpoints."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query

from squant.api.deps import OKXExchange
from squant.infra.exchange import (
    CancelOrderRequest as ExchangeCancelRequest,
)
from squant.infra.exchange import (
    OrderRequest as ExchangeOrderRequest,
)
from squant.infra.exchange import (
    OrderResponse as ExchangeOrderResponse,
)
from squant.infra.exchange import (
    TimeFrame,
)
from squant.infra.exchange.exceptions import (
    ExchangeAPIError,
    ExchangeAuthenticationError,
    ExchangeConnectionError,
    ExchangeRateLimitError,
    InvalidOrderError,
    OrderNotFoundError,
)
from squant.schemas.exchange import (
    BalanceItem,
    BalanceResponse,
    CancelOrderRequest,
    CandlestickItem,
    CandlestickResponse,
    OpenOrdersResponse,
    OrderResponse,
    PlaceOrderRequest,
    TickerResponse,
)

router = APIRouter()


def _handle_exchange_error(e: Exception) -> None:
    """Convert exchange exceptions to HTTP exceptions."""
    if isinstance(e, ExchangeAuthenticationError):
        raise HTTPException(status_code=401, detail=str(e))
    if isinstance(e, ExchangeRateLimitError):
        raise HTTPException(
            status_code=429,
            detail=str(e),
            headers={"Retry-After": str(int(e.retry_after or 1))},
        )
    if isinstance(e, OrderNotFoundError):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, InvalidOrderError):
        raise HTTPException(status_code=400, detail=str(e))
    if isinstance(e, ExchangeConnectionError):
        raise HTTPException(status_code=503, detail=str(e))
    if isinstance(e, ExchangeAPIError):
        raise HTTPException(status_code=502, detail=str(e))
    raise HTTPException(status_code=500, detail=str(e))


def _to_order_response(result: ExchangeOrderResponse) -> OrderResponse:
    """Convert exchange order response to API response."""
    return OrderResponse(
        order_id=result.order_id,
        client_order_id=result.client_order_id,
        symbol=result.symbol,
        side=result.side,
        type=result.type,
        status=result.status,
        price=result.price,
        amount=result.amount,
        filled=result.filled,
        avg_price=result.avg_price,
        created_at=result.created_at,
    )


# Balance endpoints


@router.get("/balance", response_model=BalanceResponse)
async def get_balance(exchange: OKXExchange) -> BalanceResponse:
    """Get account balance for all currencies.

    Returns the available and frozen balance for each currency in the account.
    """
    try:
        account = await exchange.get_balance()
        return BalanceResponse(
            exchange=account.exchange,
            balances=[
                BalanceItem(
                    currency=b.currency,
                    available=b.available,
                    frozen=b.frozen,
                    total=b.total,
                )
                for b in account.balances
            ],
            timestamp=account.timestamp,
        )
    except Exception as e:
        _handle_exchange_error(e)
        raise  # unreachable, but makes type checker happy


@router.get("/balance/{currency}", response_model=BalanceItem | None)
async def get_balance_currency(
    exchange: OKXExchange,
    currency: Annotated[str, Path(description="Currency symbol (e.g., BTC, USDT)")],
) -> BalanceItem | None:
    """Get balance for a specific currency.

    Returns None if the currency is not found in the account.
    """
    try:
        balance = await exchange.get_balance_currency(currency)
        if balance is None:
            return None
        return BalanceItem(
            currency=balance.currency,
            available=balance.available,
            frozen=balance.frozen,
            total=balance.total,
        )
    except Exception as e:
        _handle_exchange_error(e)
        raise


# Market data endpoints


@router.get("/ticker/{symbol:path}", response_model=TickerResponse)
async def get_ticker(
    exchange: OKXExchange,
    symbol: Annotated[str, Path(description="Trading pair (e.g., BTC/USDT)")],
) -> TickerResponse:
    """Get ticker data for a trading pair.

    Returns the latest price and 24h statistics.
    """
    try:
        ticker = await exchange.get_ticker(symbol)
        return TickerResponse(
            symbol=ticker.symbol,
            last=ticker.last,
            bid=ticker.bid,
            ask=ticker.ask,
            high_24h=ticker.high_24h,
            low_24h=ticker.low_24h,
            volume_24h=ticker.volume_24h,
            timestamp=ticker.timestamp,
        )
    except Exception as e:
        _handle_exchange_error(e)
        raise


@router.get("/tickers", response_model=list[TickerResponse])
async def get_tickers(
    exchange: OKXExchange,
    symbols: Annotated[
        str | None,
        Query(description="Comma-separated trading pairs (e.g., BTC/USDT,ETH/USDT)"),
    ] = None,
) -> list[TickerResponse]:
    """Get ticker data for multiple trading pairs.

    If no symbols specified, returns all available tickers.
    """
    try:
        symbol_list = symbols.split(",") if symbols else None
        tickers = await exchange.get_tickers(symbol_list)
        return [
            TickerResponse(
                symbol=t.symbol,
                last=t.last,
                bid=t.bid,
                ask=t.ask,
                high_24h=t.high_24h,
                low_24h=t.low_24h,
                volume_24h=t.volume_24h,
                timestamp=t.timestamp,
            )
            for t in tickers
        ]
    except Exception as e:
        _handle_exchange_error(e)
        raise


@router.get("/candles/{symbol:path}", response_model=CandlestickResponse)
async def get_candles(
    exchange: OKXExchange,
    symbol: Annotated[str, Path(description="Trading pair (e.g., BTC/USDT)")],
    timeframe: Annotated[
        str,
        Query(description="Time frame: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w"),
    ] = "1h",
    limit: Annotated[int, Query(ge=1, le=300, description="Number of candles")] = 100,
) -> CandlestickResponse:
    """Get candlestick (OHLCV) data for a trading pair.

    Returns historical price data in candlestick format.
    """
    try:
        # Map string to TimeFrame enum
        tf_map = {
            "1m": TimeFrame.M1,
            "5m": TimeFrame.M5,
            "15m": TimeFrame.M15,
            "30m": TimeFrame.M30,
            "1h": TimeFrame.H1,
            "4h": TimeFrame.H4,
            "1d": TimeFrame.D1,
            "1w": TimeFrame.W1,
        }
        tf = tf_map.get(timeframe)
        if tf is None:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid timeframe: {timeframe}. Valid values: {', '.join(tf_map.keys())}",
            )

        candles = await exchange.get_candlesticks(symbol, tf, limit=limit)
        return CandlestickResponse(
            symbol=symbol,
            timeframe=timeframe,
            candles=[
                CandlestickItem(
                    timestamp=c.timestamp,
                    open=c.open,
                    high=c.high,
                    low=c.low,
                    close=c.close,
                    volume=c.volume,
                )
                for c in candles
            ],
        )
    except HTTPException:
        raise
    except Exception as e:
        _handle_exchange_error(e)
        raise


# Order endpoints


@router.post("/orders", response_model=OrderResponse, status_code=201)
async def place_order(
    exchange: OKXExchange,
    request: PlaceOrderRequest,
) -> OrderResponse:
    """Place a new order.

    For limit orders, price is required.
    For market orders, price should be omitted.
    """
    try:
        order_request = ExchangeOrderRequest(
            symbol=request.symbol,
            side=request.side,
            type=request.type,
            amount=request.amount,
            price=request.price,
            client_order_id=request.client_order_id,
        )
        result = await exchange.place_order(order_request)
        return _to_order_response(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        _handle_exchange_error(e)
        raise


@router.post("/orders/cancel", response_model=OrderResponse)
async def cancel_order(
    exchange: OKXExchange,
    request: CancelOrderRequest,
) -> OrderResponse:
    """Cancel an existing order.

    Either order_id or client_order_id must be provided.
    """
    if not request.order_id and not request.client_order_id:
        raise HTTPException(
            status_code=400,
            detail="Either order_id or client_order_id must be provided",
        )

    try:
        cancel_request = ExchangeCancelRequest(
            symbol=request.symbol,
            order_id=request.order_id,
            client_order_id=request.client_order_id,
        )
        result = await exchange.cancel_order(cancel_request)
        return _to_order_response(result)
    except Exception as e:
        _handle_exchange_error(e)
        raise


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    exchange: OKXExchange,
    order_id: Annotated[str, Path(description="Exchange order ID")],
    symbol: Annotated[str, Query(description="Trading pair")],
) -> OrderResponse:
    """Get order details by ID."""
    try:
        result = await exchange.get_order(symbol, order_id)
        return _to_order_response(result)
    except Exception as e:
        _handle_exchange_error(e)
        raise


@router.get("/orders", response_model=OpenOrdersResponse)
async def get_open_orders(
    exchange: OKXExchange,
    symbol: Annotated[str | None, Query(description="Filter by trading pair")] = None,
) -> OpenOrdersResponse:
    """Get all open (unfilled) orders.

    Optionally filter by trading pair.
    """
    try:
        orders = await exchange.get_open_orders(symbol)
        return OpenOrdersResponse(
            orders=[_to_order_response(o) for o in orders],
            total=len(orders),
        )
    except Exception as e:
        _handle_exchange_error(e)
        raise
