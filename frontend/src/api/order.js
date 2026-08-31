import api from '@/api/index.js';
import Product from '@/models/Product.js';

// Everything the buying half of the storefront talks to: the checkout, the cart's own lines and
// the two token pages (purchases, unsubscribe). Errors are deliberately not caught here - the
// form that started a request is the only place that can tell the customer what happened.

// An order holds a product at most once and there are no quantities (ADR-0001), so the checkout
// payload is a list of ids. The language rides along because the delivery e-mail is sent from the
// payment webhook, long after this browser is gone (ADR-0004).
export async function createOrder({email, language, products}) {
    const response = await api.post('/order/', {email, language, products});
    return response.data.redirect_url;
}

// The cart lives in localStorage, so the server is asked what those ids are now: a product taken
// off the shelf is simply absent from the answer, and a price that moved arrives corrected.
export async function fetchCartItems(ids) {
    if (!ids.length) return [];
    const {data} = await api.get('/cart/items/', {params: {ids: ids.join(',')}});
    return data.map(item => new Product(item));
}

export async function sendPurchasesLinks({email, language}) {
    return (await api.post('/send-links/', {email, language})).data;
}

// The token in the path is the whole authentication (ADR-0002): a 404 from any of these means the
// link is spent, and the page says so instead of retrying.
export async function fetchPurchases(token) {
    return (await api.get(`/purchases/${token}/`)).data;
}

export async function refreshPurchaseItem(token, itemId) {
    return (await api.post(`/purchases/${token}/refresh/${itemId}/`)).data;
}

export async function refreshAllPurchaseItems(token) {
    return (await api.post(`/purchases/${token}/refresh-all/`)).data;
}

// GET only reads the token and answers who it belongs to; POST is the only thing that opts anyone
// out - inboxes pre-fetch every link in a message.
export async function fetchSubscription(token) {
    return (await api.get(`/unsubscribe/${token}/`)).data;
}

export async function unsubscribe(token) {
    return (await api.post(`/unsubscribe/${token}/`)).data;
}
