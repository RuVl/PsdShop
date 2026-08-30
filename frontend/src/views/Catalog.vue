<script setup>
import {computed, nextTick, ref, watch} from 'vue';
import {useRoute, useRouter} from 'vue-router';
import CountrySidebar from '@/components/storefront/CountrySidebar.vue';
import Pagination from '@/components/storefront/Pagination.vue';
import ProductCard from '@/components/storefront/ProductCard.vue';
import SlidesCarousel from '@/components/storefront/SlidesCarousel.vue';
import IconCross from '@/components/icons/IconCross.vue';
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
const searchQuery = computed(() => route.query.q || '');

const isHome = computed(() => countrySlug.value === 'all' && typeSlug.value === 'all');
const isFiltered = computed(() => !isHome.value);

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
const state = ref('loading');
const notFound = ref(false);
const gridTop = ref(null);

// One page on screen and that page in the address, the way the bot page has always worked.
// Infinite scroll used to hold a range of pages here; it cost a scroll anchor, two observers and
// a guess at the reader's direction, and it left `?page=` describing something other than what
// was on screen.
const page = computed(() => Math.max(1, Number(route.query.page) || 1));
const totalPages = computed(() => Math.max(1, Math.ceil(count.value / PAGE_SIZE)));

// What the grid is showing, as the API takes it. The search rides along with the facets: it is
// the server that filters, so the count the pagination reads stays honest.
function facetParams() {
    return {country: countrySlug.value, type: typeSlug.value, q: searchQuery.value};
}

function gridKey() {
    return `${route.params.country || 'all'}/${route.params.type || 'all'}/${route.query.q || ''}/${page.value}`;
}

// The address of a page of this listing: everything else in the query stays, and page 1 carries
// no parameter at all - that is the canonical address of the listing.
function pageRoute(number) {
    const query = {...route.query};
    if (number > 1) query.page = String(number);
    else delete query.page;

    return {query};
}

async function load() {
    state.value = 'loading';
    notFound.value = false;
    const facet = facetParams();
    const target = page.value;

    try {
        let data;
        try {
            data = await fetchProducts({...facet, page: target});
        } catch (error) {
            // The API answers 404 both for an unknown country/type slug and for a page past the
            // end. Asking for the first page tells the two apart: if it answers, the listing
            // exists and the reader simply overshot - send them to the last real page instead of
            // a dead end, address included, so a reload shows the same grid.
            if (error.response?.status !== 404 || target <= 1) throw error;

            data = await fetchProducts({...facet, page: 1});
            router.replace(pageRoute(Math.max(1, Math.ceil(data.count / PAGE_SIZE))));
            return;
        }

        count.value = data.count;
        products.value = data.results;
        state.value = 'ready';
        await nextTick();
        scrollToGrid();
    } catch (error) {
        // Still a 404 with the first page asked for: this country or type does not exist.
        if (error.response?.status === 404) notFound.value = true;
        else state.value = 'failed';
    }
}

// Landing on the front page belongs at the top of the document - the hero and the slider are part
// of it. Every page change after that belongs at the cards, under the fixed header.
let firstLoad = true;

const READER_EVENTS = ['wheel', 'touchstart', 'keydown', 'pointerdown'];

function scrollToGrid() {
    const landing = firstLoad && page.value === 1;
    firstLoad = false;
    if (landing || !gridTop.value) return;

    const card = gridTop.value.firstElementChild;
    if (!card) return;

    // `behavior: "instant"` on purpose: style.css puts `scroll-behavior: smooth` on <html>, and an
    // animated scroll both lands late and dies on the reader's first wheel.
    const pin = () => {
        const header = document.querySelector('.header')?.getBoundingClientRect().height ?? 0;
        const top = Math.max(0, Math.round(window.scrollY + card.getBoundingClientRect().top - header - 16));
        if (Math.abs(window.scrollY - top) > 1) window.scrollTo({top, behavior: 'instant'});
    };

    // One scroll is not enough on a cold cache: the hero and the slide above the grid get their
    // pictures after the first paint and push the cards down again. Hold the card in place for a
    // moment, and step aside as soon as the reader touches the page.
    let released = false;
    const release = () => {
        released = true;
        for (const event of READER_EVENTS) window.removeEventListener(event, release);
    };
    for (const event of READER_EVENTS) window.addEventListener(event, release, {passive: true});

    const deadline = performance.now() + 1500;
    const step = () => {
        if (released || !card.isConnected) return release();

        pin();
        if (performance.now() < deadline) requestAnimationFrame(step);
        else release();
    };
    step();
}

watch(() => gridKey(), load, {immediate: true});

// The search lives in the URL (`?q=`), and the URL is what the grid loads from - the field below
// is only the way a reader edits it.
const queryInput = ref(searchQuery.value);
const searchInput = ref(null);
let searchTimer = null;

function pushQuery(value) {
    const query = {...route.query};
    const trimmed = value.trim();
    if (trimmed) query.q = trimmed;
    else delete query.q;

    if ((route.query.q || '') === (query.q || '')) return;
    // A new search starts at the top of its own results, not on page 7 of the previous one.
    delete query.page;
    router.replace({query});
}

watch(queryInput, value => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => pushQuery(value), 300);
});

// Back/forward, a facet change and the reset chip all arrive here.
watch(searchQuery, value => {
    if (value !== queryInput.value.trim()) queryInput.value = value;
});

// The magnifier is a button: with an empty field it puts the cursor in it, with a query it turns
// into a cross and clears it. Waiting out the debounce to clear would feel broken.
function onSearchIcon() {
    if (queryInput.value) {
        clearTimeout(searchTimer);
        queryInput.value = '';
        pushQuery('');
    }
    searchInput.value?.focus();
}

// Every facet link carries the search over: choosing a country is narrowing the same search, not
// starting again. `page` is deliberately dropped - a new selection starts at its first page.
function catalogTarget(country, type) {
    const query = searchQuery.value ? {q: searchQuery.value} : {};
    if (country === 'all' && type === 'all') return {name: 'home', params: {lang: lang.value}, query};
    return {name: 'catalog', params: {lang: lang.value, country, type}, query};
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
            <input ref="searchInput" v-model="queryInput" type="search" class="search__input" id="search-input"
                   :placeholder="$t('storefront.search.products_placeholder')"
                   @search="queryInput = $event.target.value">
            <button class="search__icon-btn" type="button"
                    :aria-label="queryInput ? $t('storefront.search.clear') : $t('storefront.search.submit')"
                    @click="onSearchIcon">
              <IconCross v-if="queryInput" class="search__icon-glyph"/>
              <IconSearch v-else class="search__icon-glyph"/>
            </button>
          </div>
        </form>

        <div class="shop__body">
          <CountrySidebar :country-slug="countrySlug" :type-slug="typeSlug"/>

          <div class="shop__right-block">
            <div class="text black">{{ $t('storefront.grid.title') }}</div>
            <div class="products section">
              <div class="products__head">
                <h2 class="title-section title black">
                  {{ selectedCountry ? selectedCountry.name : $t('storefront.grid.all_products') }}
                  <template v-if="selectedType"> — {{ selectedType.name }}</template>
                </h2>
                <!-- What is selected is only obvious once there is a way out of it. -->
                <router-link v-if="isFiltered" class="products__reset text-small" :to="catalogTarget('all', 'all')">
                  <span aria-hidden="true">×</span> {{ $t('storefront.filter.reset') }}
                </router-link>
              </div>

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
                <div ref="gridTop" class="products-list">
                  <ProductCard v-for="product in products" :key="product.id" :product="product"
                               :type-name="typeNames[product.document_type] || ''"/>
                  <p v-if="!products.length" class="text black">{{ $t('storefront.grid.empty') }}</p>
                </div>

                <Pagination :page="page" :total-pages="totalPages" :to="pageRoute"/>
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

/* The field is a `search` input, so Chrome draws its own clear cross - next to ours, which does
   the same thing and also drops `?q=` from the URL. */
.search__input::-webkit-search-cancel-button {
  display: none;
}

.search__icon-btn {
  position: absolute;
  /* 16px of the input's own margin plus half the gap between the input and the icon - the same
     23px the design puts on .search__icon. */
  top: 23px;
  right: 15px;
  width: 42px;
  height: 42px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  color: #2136ff;
  background: none;
  border: 0;
  border-radius: 50%;
  cursor: pointer;
  transition: background .3s, color .3s;
}

.search__icon-btn:hover {
  background: rgba(63, 47, 241, .08);
}

.search__icon-glyph {
  width: 18px;
  height: 18px;
}

.products__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
}

.products__reset {
  flex: none;
  color: rgba(0, 0, 0, .5);
  transition: color .3s;
}

.products__reset:hover {
  color: var(--primary);
}

/* The design marked the active filter through `input:checked + span`; these are router-links, so
   the state has to be painted on the class the router does not give either. */
.filter-products-btn.current {
  color: var(--primary);
  font-weight: var(--bold);
}
</style>
