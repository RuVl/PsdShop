import {defineStore} from 'pinia';
import {fetchCartItems} from '@/api/order.js';
import Product from '@/models/Product.js';

// A cart line is a product payload from the catalog API (both languages ride along). A product
// is a template sold any number of times, but an order holds it at most once (ADR-0001), so
// there are no quantities - the cart is a set.
export const useCartStore = defineStore('cart', {
    state: () => ({
        items: [],
    }),
    getters: {
        cartItems: state => state.items,
        cartItemCount: state => state.items.length,
        totalPrice: state => state.items.reduce((total, item) => total + Number(item.price), 0),
    },
    actions: {
        addItem(product) {
            if (!this.items.some(item => item.id === product.id)) this.items.push(product);
        },
        removeItem(id) {
            const index = this.items.findIndex(item => item.id === id);
            if (index !== -1) this.items.splice(index, 1);
        },
        inCart(id) {
            return this.items.some(item => item.id === id);
        },
        clearCart() {
            this.items = [];
        },
        // What the browser remembers can be months old: a product may be off the shelf and a price
        // may have moved, and the invoice is written from the catalog, not from localStorage. The
        // server answers with the same card payload the grid hands out, so the lines are replaced
        // wholesale; anything it does not answer for is no longer on sale and leaves the cart.
        async refresh() {
            if (!this.items.length) return;

            const fresh = await fetchCartItems(this.items.map(item => item.id));
            const byId = new Map(fresh.map(product => [product.id, product]));

            this.items = this.items.map(item => byId.get(item.id)).filter(Boolean);
        },
    },
    // localStorage can only hold JSON, so the lines come back as plain objects and have to be
    // turned into products again - otherwise `item.name` (a getter on the class) is undefined
    // until the first refresh() replaces them.
    persist: {
        afterHydrate: ({store}) => {
            store.items = store.items.map(item => (item instanceof Product ? item : new Product(item)));
        },
    },
});
