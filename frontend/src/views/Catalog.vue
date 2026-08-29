<script setup>
import {computed, nextTick, onBeforeUnmount, onMounted, ref, watch} from 'vue';
import {useRoute, useRouter} from 'vue-router';
import CountrySidebar from '@/components/storefront/CountrySidebar.vue';
import ProductCard from '@/components/storefront/ProductCard.vue';
import SlidesCarousel from '@/components/storefront/SlidesCarousel.vue';
import IconSearch from '@/components/icons/IconSearch.vue';
import {fetchProducts} from '@/api/catalog.js';
import {fetchPage} from '@/api/content.js';
import {useCatalogStore} from '@/stores/catalog.js';

// The home page and every country/type listing - the SPA presentation of the same URLs the
// bot pages render (storefront/catalog.html). Markup per design/index.html.
const route = useRoute();
const router = useRouter();
const catalogStore = useCatalogStore();

catalogStore.load();

const lang = computed(() => route.params.lang || 'en');
const countrySlug = computed(() => route.params.country || 'all');
const typeSlug = computed(() => route.params.type || 'all');

const isHome = computed(() => countrySlug.value === 'all' && typeSlug.value === 'all');

const selectedCountry = computed(() => catalogStore.countries.find(c => c.slug === countrySlug.value) || null);
const selectedType = computed(() => catalogStore.documentTypes.find(t => t.slug === typeSlug.value) || null);

// The owner-written SEO block of the front page (the `home` content.Page row).
const homePage = ref(null);
watch(isHome, async (home) => {
    if (home && !homePage.value) homePage.value = await fetchPage('home').catch(() => null);
}, {immediate: true});
const typeNames = computed(() => Object.fromEntries(catalogStore.documentTypes.map(t => [t.slug, t.name])));

// Grid state: loading, failed and empty must never look alike.
const PAGE_SIZE = 24;

const products = ref([]);
const count = ref(0);
// The grid holds a range of pages, not one: a visitor who scrolled to page 7 and reloaded must
// see the same list, and the pages above it are still reachable.
const firstPage = ref(1);
const lastPage = ref(1);
const state = ref('loading');
const loadingMore = ref(false);
const loadingPrevious = ref(false);
const notFound = ref(false);

const totalPages = computed(() => Math.max(1, Math.ceil(count.value / PAGE_SIZE)));
const hasNext = computed(() => products.value.length > 0 && lastPage.value < totalPages.value);
const hasPrevious = computed(() => firstPage.value > 1);

function facetKey() {
    return `${route.params.country || 'all'}/${route.params.type || 'all'}`;
}

async function loadFirst(target) {
    state.value = 'loading';
    notFound.value = false;
    const facet = {country: countrySlug.value, type: typeSlug.value};

    try {
        let data;
        try {
            data = await fetchProducts({...facet, page: target});
        } catch (error) {
            // The API answers 404 both for an unknown country/type slug and for a page past the
            // end. Asking for the first page tells the two apart: if it answers, the listing
            // exists and the reader simply overshot - land them on the last real page instead of
            // a dead end, which is what `?page=999` used to look like.
            if (error.response?.status !== 404 || target <= 1) throw error;

            data = await fetchProducts({...facet, page: 1});
            target = Math.max(1, Math.ceil(data.count / PAGE_SIZE));
            if (target > 1) data = await fetchProducts({...facet, page: target});
        }

        count.value = data.count;
        products.value = data.results;
        firstPage.value = target;
        lastPage.value = target;
        state.value = 'ready';
        syncPageInUrl();
    } catch (error) {
        // Still a 404 with the first page asked for: this country or type does not exist.
        if (error.response?.status === 404) notFound.value = true;
        else state.value = 'failed';
    }
}

async function loadMore() {
    if (loadingMore.value || state.value !== 'ready' || !hasNext.value) return;
    loadingMore.value = true;
    try {
        const next = lastPage.value + 1;
        const data = await fetchProducts({country: countrySlug.value, type: typeSlug.value, page: next});
        count.value = data.count;
        products.value = [...products.value, ...data.results];
        lastPage.value = next;
        syncPageInUrl();
    } catch {
        // Nothing more to add: stop offering the button rather than shouting at the reader.
        count.value = products.value.length;
    } finally {
        loadingMore.value = false;
    }
}

async function loadPrevious() {
    if (loadingPrevious.value || state.value !== 'ready' || !hasPrevious.value) return;
    loadingPrevious.value = true;
    const heightBefore = document.documentElement.scrollHeight;
    const scrollBefore = window.scrollY;
    try {
        const previous = firstPage.value - 1;
        const data = await fetchProducts({country: countrySlug.value, type: typeSlug.value, page: previous});
        count.value = data.count;
        products.value = [...data.results, ...products.value];
        firstPage.value = previous;
        // Prepending moves everything down; hold the reader where they were looking.
        await nextTick();
        window.scrollTo({top: scrollBefore + (document.documentElement.scrollHeight - heightBefore)});
    } catch {
        firstPage.value = 1;
    } finally {
        loadingPrevious.value = false;
    }
}

// The URL keeps the last loaded page, so a reload or a shared link lands on the same grid a bot
// would be served at `?page=N`.
function syncPageInUrl() {
    const query = {...route.query};
    if (lastPage.value > 1) query.page = String(lastPage.value);
    else delete query.page;

    if ((route.query.page || '') !== (query.page || '')) router.replace({query});
}

watch(
    () => facetKey(),
    () => {
        products.value = [];
        loadFirst(Number(route.query.page) || 1);
    },
    {immediate: true},
);

// Infinite scroll in both directions: the two buttons click themselves when they scroll into
// view, and stay as the fallback for a browser (or a moment) where the observer does not fire.
const loadMoreBlock = ref(null);
const loadPreviousBlock = ref(null);
let observer = null;

onMounted(() => {
    observer = new IntersectionObserver(entries => {
        for (const entry of entries) {
            if (!entry.isIntersecting) continue;
            if (entry.target === loadMoreBlock.value) loadMore();
            if (entry.target === loadPreviousBlock.value) loadPrevious();
        }
    });

    for (const element of [loadMoreBlock, loadPreviousBlock]) {
        watch(element, (node, previous) => {
            if (previous) observer.unobserve(previous);
            if (node) observer.observe(node);
        }, {immediate: true});
    }
});
onBeforeUnmount(() => observer?.disconnect());

// The product search filters the loaded cards, like the design's app.js did - but it lives in the
// URL (`?q=`), so a reload or a shared link keeps it. The canonical link drops every parameter
// except `page`, so this never becomes a second address for the same listing.
const productQuery = ref(route.query.q || '');
let searchTimer = null;

watch(productQuery, value => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
        const query = {...route.query};
        const trimmed = value.trim();
        if (trimmed) query.q = trimmed;
        else delete query.q;

        if ((route.query.q || '') !== (query.q || '')) router.replace({query});
    }, 300);
});

// Back/forward, a cleared field and a facet change all arrive here.
watch(() => route.query.q, value => {
    if ((value || '') !== productQuery.value.trim()) productQuery.value = value || '';
});

const visibleProducts = computed(() => {
    const query = productQuery.value.trim().toLowerCase();
    if (!query) return products.value;
    return products.value.filter(product => product.name.toLowerCase().includes(query));
});

function catalogTarget(country, type) {
    if (country === 'all' && type === 'all') return {name: 'home', params: {lang: lang.value}};
    return {name: 'catalog', params: {lang: lang.value, country, type}};
}
</script>

<template>
  <main class="main-content">
    <SlidesCarousel v-if="isHome"/>

    <div v-if="notFound" class="container">
      <p class="text black">{{ $t('storefront.grid.not_found') }}</p>
    </div>

    <section v-else class="shop mb-60">
      <div class="container">
        <form class="search" @submit.prevent>
          <label for="search-input" class="search__title text black">{{ $t('storefront.search.products') }}</label>
          <div class="search__wrap">
            <input v-model="productQuery" type="search" class="search__input" id="search-input"
                   :placeholder="$t('storefront.search.products_placeholder')"
                   @search="productQuery = $event.target.value">
            <IconSearch class="search__icon-svg"/>
          </div>
        </form>

        <div class="shop__body">
          <CountrySidebar :country-slug="countrySlug" :type-slug="typeSlug"/>

          <div class="shop__right-block">
            <div class="text black">{{ $t('storefront.grid.title') }}</div>
            <div class="products section">
              <h2 class="title-section title black">
                {{ selectedCountry ? selectedCountry.name : $t('storefront.grid.all_products') }}
                <template v-if="selectedType"> — {{ selectedType.name }}</template>
              </h2>

              <div class="filter-products">
                <div class="text-small black">{{ $t('storefront.filter.title') }}</div>
                <div class="filter-products-content">
                  <div class="filter-products-right">
                    <div class="filter-products-card-list">
                      <router-link class="filter-products-card-list-item filter-products-btn"
                                   :class="{current: typeSlug === 'all'}" :to="catalogTarget(countrySlug, 'all')">
                        {{ $t('storefront.filter.all_categories') }}
                      </router-link>
                      <router-link v-for="dtype in catalogStore.documentTypes" :key="dtype.slug"
                                   class="filter-products-card-list-item filter-products-btn"
                                   :class="{current: dtype.slug === typeSlug}"
                                   :to="catalogTarget(countrySlug, dtype.slug)">
                        {{ dtype.name }}
                      </router-link>
                    </div>
                  </div>
                </div>
              </div>

              <p v-if="state === 'loading'" class="text black">{{ $t('products.loading') }}</p>
              <p v-else-if="state === 'failed'" class="text black">{{ $t('products.error') }}</p>
              <template v-else>
                <div v-if="hasPrevious" ref="loadPreviousBlock" class="load-more load-more--previous">
                  <button class="btn btn-grade text white opacity" type="button" :disabled="loadingPrevious"
                          @click="loadPrevious">
                    {{ loadingPrevious ? $t('products.loading') : $t('storefront.grid.load_previous') }}
                  </button>
                </div>

                <div class="products-list">
                  <ProductCard v-for="product in visibleProducts" :key="product.id" :product="product"
                               :type-name="typeNames[product.document_type] || ''"/>
                  <p v-if="!visibleProducts.length" class="text black">{{ $t('storefront.grid.empty') }}</p>
                </div>

                <div v-if="hasNext" class="load-more">
                  <button class="btn btn-grade text white opacity" type="button" :disabled="loadingMore"
                          @click="loadMore">
                    {{ loadingMore ? $t('products.loading') : $t('storefront.grid.load_more') }}
                  </button>
                </div>
                <!-- The observer watches this line, not the button: the button stays a button, and
                     a reader who scrolls here gets the next page without pressing it. -->
                <div v-if="hasNext" ref="loadMoreBlock" class="load-more-sentinel" aria-hidden="true"></div>
              </template>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section v-if="selectedCountry?.seo_text_en || selectedType?.seo_text_en || (isHome && homePage)"
             class="seo mb-60" id="seo">
      <div class="container">
        <div class="idesc">
          <!-- Owner-authored HTML from the admin editor (the `home` content.Page row). -->
          <div v-if="isHome && homePage" v-html="homePage.body"></div>
          <p v-if="selectedCountry && selectedCountry.seo_text">{{ selectedCountry.seo_text }}</p>
          <p v-if="selectedType && selectedType.seo_text">{{ selectedType.seo_text }}</p>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped>
/* The design puts the icon inside the input, which itself sits 16px below the label
   (.search__input has margin-top). Centring on the wrapper would lift it by half of that. */
.search__wrap {
  position: relative;
}

.search__icon-svg {
  position: absolute;
  /* 16px of the input's own margin plus half the gap between the input and the icon - the same
     23px the design puts on .search__icon. */
  top: 23px;
  right: 15px;
  width: 42px;
  height: 42px;
  padding: 10px;
  color: #2136ff;
  pointer-events: none;
}

.load-more {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}

.load-more--previous {
  margin: 0 0 24px;
}

/* Zero-height trigger below the button: the observer fires slightly before the reader arrives. */
.load-more-sentinel {
  height: 1px;
  margin-top: 120px;
}
</style>
