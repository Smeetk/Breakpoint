# Breakpoint

## Target application: Demo Store

Run with `python server.py` and open http://localhost:8000. Demo credentials: `demo@breakpoint.local` / `demo123`.

Routes: `/login`, `/products`, `/product/:id`, `/cart`, `/checkout`, `/order-success` (the app uses hash navigation for static hosting).

Reset the demo with `POST http://localhost:8000/api/reset`.

Playwright selectors include `add-to-cart`, `cart-item`, `quantity-increase`, `quantity-decrease`, `cart-total`, `checkout-button`, and `checkout-total` (all as `data-testid`).
