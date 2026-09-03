import {defineStore} from 'pinia';
import {fetchPages, fetchSettings, fetchSlides} from '@/api/content.js';

// Header/footer data (menu pages, site settings) fetched once per visit; slides on demand.
export const useContentStore = defineStore('content', {
    state: () => ({
        pages: [],
        settings: null,
        slides: [],
        loaded: false,
        slidesLoaded: false,
        failed: false,
    }),
    actions: {
        async load() {
            if (this.loaded) return;
            this.failed = false;
            try {
                [this.pages, this.settings] = await Promise.all([fetchPages(), fetchSettings()]);
                this.loaded = true;
            } catch {
                // The chrome degrades to the bare menu and the pages themselves still answer, so
                // this is not worth a message across the page. It is recorded rather than dropped:
                // `loaded` alone cannot tell "the owner wrote no pages" from "the API is down",
                // and the next thing to ask that question deserves an answer.
                this.failed = true;
            }
        },
        async loadSlides() {
            if (this.slidesLoaded) return;
            try {
                this.slides = await fetchSlides();
                this.slidesLoaded = true;
            } catch {
                // No slider is a valid state - the front page works without it.
            }
        },
    },
});
