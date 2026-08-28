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
