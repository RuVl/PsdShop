import {defineStore} from 'pinia';

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
    },
    persist: true,
});
