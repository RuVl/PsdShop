// Header cart badge. The cart lives in localStorage (ADR-0009); this island only reads it and
// paints the count into #cart-counter. Key `cart` is the pinia-persist store id used by the cart.
const KEY = 'cart';

function cartCount() {
    try {
        const raw = localStorage.getItem(KEY);
        if (!raw) return 0;
        const data = JSON.parse(raw);
        return Array.isArray(data.items) ? data.items.length : 0;
    } catch {
        // A private window or malformed value must not break the header.
        return 0;
    }
}

function render() {
    const el = document.getElementById('cart-counter');
    if (!el) return;

    const count = cartCount();
    if (count > 0) {
        el.textContent = String(count);
        el.hidden = false;
    } else {
        el.hidden = true;
    }
}

render();

// Another tab changed the cart (storage event fires cross-tab; key is null on clear()).
window.addEventListener('storage', (event) => {
    if (event.key === KEY || event.key === null) render();
});
