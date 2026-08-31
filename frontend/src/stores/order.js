import {defineStore} from 'pinia';
import {createOrder} from '@/api/order.js';
import {useCartStore} from '@/stores/cart.js';
import {useSettingsStore} from '@/stores/settings.js';

// Two ways to buy, one request: the whole cart, or a single product bought without ever touching
// the cart ("buy now"). Plisio is the only provider, so there is nothing to choose between.
export const useOrderStore = defineStore('order', {
    actions: {
        async _checkout(email, products) {
            return createOrder({email, language: useSettingsStore().currentLanguage, products});
        },
        async buyCart(email) {
            const cart = useCartStore();
            const redirectUrl = await this._checkout(email, cart.cartItems.map(item => item.id));

            // Only once the invoice exists: a refused checkout must leave the cart alone.
            cart.clearCart();
            window.location.href = redirectUrl;
        },
        async buyProduct(product, email) {
            window.location.href = await this._checkout(email, [product.id]);
        },
    },
});
