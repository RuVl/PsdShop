import {defineStore} from 'pinia';
import {fetchCountries, fetchDocumentTypes} from '@/api/catalog.js';

// Sidebar and filter data: fetched once per visit, shared by every catalog page.
export const useCatalogStore = defineStore('catalog', {
    state: () => ({
        countries: [],
        documentTypes: [],
        loaded: false,
        failed: false,
    }),
    getters: {
        popularCountries: state => state.countries.filter(country => country.is_popular),
        // A product payload names its country by slug alone - the flag and the localised name live
        // on the country row. The cart lines are what read it: they draw a product the grid never
        // handed them, straight out of localStorage (views/Cart.vue).
        countryBySlug: state => slug => state.countries.find(country => country.slug === slug) || null,
    },
    actions: {
        async load() {
            if (this.loaded) return;
            this.failed = false;
            try {
                [this.countries, this.documentTypes] = await Promise.all([fetchCountries(), fetchDocumentTypes()]);
                this.loaded = true;
            } catch {
                this.failed = true;
            }
        },
    },
});
