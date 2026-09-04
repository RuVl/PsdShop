import {computed} from 'vue';
import {useRoute} from 'vue-router';

/**
 * Where a facet link goes.
 *
 * One rule, because three places need it and they had drifted apart in wording if not yet in
 * behaviour: the sidebar, the type chips and the reset link. It says two things. `all`/`all` is
 * the home page - that is the canonical address of the unfiltered listing, and Django 301s
 * `/all/all/` to it. And an active `?q=` is carried over, because picking a country narrows the
 * same search rather than starting a new one, while `page` is dropped: a new selection starts at
 * its first page.
 */
export function useCatalogLinks() {
    const route = useRoute();

    const lang = computed(() => route.params.lang || 'en');
    const searchQuery = computed(() => route.query.q || '');

    function catalogTarget(country, type) {
        const query = searchQuery.value ? {q: searchQuery.value} : {};
        if (country === 'all' && type === 'all') return {name: 'home', params: {lang: lang.value}, query};

        return {name: 'catalog', params: {lang: lang.value, country, type}, query};
    }

    return {lang, searchQuery, catalogTarget};
}
