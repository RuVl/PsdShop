import Localized from '@/models/Localized.js';

// One catalog card, or the whole product page when the detail endpoint filled it in. A product is
// a template sold any number of times (ADR-0001): no stock, no quantity, and the price is USD.
export default class Product extends Localized {
    static translated = ['name', 'description'];

    /** `$12.50` - the one place a price becomes text. */
    get priceLabel() {
        return `$${Number(this.price).toFixed(2)}`;
    }

    /** A router target for this product; the `<id>-<slug>` segment is built by the server. */
    route(lang) {
        return {
            name: 'product',
            params: {
                lang,
                country: this.country,
                type: this.document_type,
                productSlug: this.url_slug,
            },
        };
    }
}

Product.defineTranslations();
