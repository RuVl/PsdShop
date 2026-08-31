import {getI18n} from '@/i18n/index.js';

// Every catalog and content payload carries both languages (`name_en` / `name_ru`), so the SPA
// switches language without refetching. This base turns that pair into one property: `name`.
//
// The locale is read on access rather than captured, because these objects outlive a render -
// they sit in stores and in the cart - and the language changes under them.
export default class Localized {
    /**
     * Declare which fields arrive translated. `['name']` gives a `name` getter reading
     * `name_<locale>` with an English fallback - the same rule modeltranslation applies server-side.
     */
    static translated = [];

    constructor(data = {}) {
        Object.assign(this, data);
    }

    /** The raw payload, for anything that has to be stored as plain JSON (the cart). */
    toJSON() {
        return {...this};
    }

    static defineTranslations() {
        for (const field of this.translated) {
            Object.defineProperty(this.prototype, field, {
                get() {
                    const locale = getI18n()?.global.locale.value || 'en';
                    return this[`${field}_${locale}`] || this[`${field}_en`] || '';
                },
                configurable: true,
            });
        }
    }
}
