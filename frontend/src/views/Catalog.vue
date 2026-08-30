<script setup>
import {computed, nextTick, onBeforeUnmount, onMounted, ref, watch} from 'vue';
import {useRoute, useRouter} from 'vue-router';
import CountrySidebar from '@/components/storefront/CountrySidebar.vue';
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
// The grid holds a range of pages, not one: a visitor who scrolled to page 7 and reloaded must
// see the same list, and the pages above it are still reachable.
const firstPage = ref(1);
const lastPage = ref(1);
const state = ref('loading');
const loadingMore = ref(false);
const loadingPrevious = ref(false);
const notFound = ref(false);
const gridTop = ref(null);
// Until the reader moves the page themselves, an intersection above the grid is the layout
// settling (pictures arriving, the grid being pinned), not a scroll upwards - and pulling the
// previous page in on that would drag them off the page they asked for.
const readerMoved = ref(false);
const READER_EVENTS = ['wheel', 'touchstart', 'keydown', 'pointerdown'];

const totalPages = computed(() => Math.max(1, Math.ceil(count.value / PAGE_SIZE)));
const hasNext = computed(() => products.value.length > 0 && lastPage.value < totalPages.value);
const hasPrevious = computed(() => firstPage.value > 1);

// What the grid is showing, as the API takes it. The search rides along with the facets: it is
// the server that filters, so the counts the buttons read stay honest.
function facetParams() {
    return {country: countrySlug.value, type: typeSlug.value, q: searchQuery.value};
}

function facetKey() {
    return `${route.params.country || 'all'}/${route.params.type || 'all'}/${route.query.q || ''}`;
}

async function loadFirst(target) {
    state.value = 'loading';
    notFound.value = false;
    const facet = facetParams();

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

        // Arriving at `?page=5` used to land at the very top of the document, with the products
        // somewhere below the fold - the reader had to scroll down to them before scrolling back
        // up made sense. Put the cards at the top of the screen instead. The scroll stops at the
        // grid rather than at the whole block, so "load previous" stays just above the fold and
        // nothing loads itself until the reader actually moves up.
        if (target > 1) {
            await nextTick();
            anchorGrid();
        }
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
        const data = await fetchProducts({...facetParams(), page: next});
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

async function loadPrevious({auto = false} = {}) {
    if (auto && !readerMoved.value) return;
    if (loadingPrevious.value || state.value !== 'ready' || !hasPrevious.value) return;
    loadingPrevious.value = true;
    const heightBefore = document.documentElement.scrollHeight;
    const scrollBefore = window.scrollY;
    try {
        const previous = firstPage.value - 1;
        const data = await fetchProducts({...facetParams(), page: previous});
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

// Holding the grid at the top of the screen takes more than one scroll: the hero and the slide
// above it get their pictures after the first paint and push everything down. Keep re-pinning
// until the layout stops growing, and step aside the moment the reader touches the page.
function anchorGrid() {
    const pin = () => gridTop.value?.scrollIntoView({block: 'start'});
    pin();

    const resize = new ResizeObserver(pin);
    resize.observe(document.body);

    let timer = null;
    const release = () => {
        resize.disconnect();
        clearTimeout(timer);
        for (const event of READER_EVENTS) window.removeEventListener(event, release);
    };

    timer = setTimeout(release, 2000);
    for (const event of READER_EVENTS) window.addEventListener(event, release, {passive: true});
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

// A record is a photograph of a past frame. Landing on `?page=5` renders a short page - no
// images yet - so "load previous" starts on screen, is photographed there, and the record is
// delivered after the grid has already been scrolled into place. Ask the element where it is now.
function onScreen(node) {
    if (!node) return false;
    const rect = node.getBoundingClientRect();
    return rect.bottom > 0 && rect.top < window.innerHeight;
}

onMounted(() => {
    const moved = () => { readerMoved.value = true; };
    for (const event of READER_EVENTS) window.addEventListener(event, moved, {passive: true});
    onBeforeUnmount(() => {
        for (const event of READER_EVENTS) window.removeEventListener(event, moved);
    });

    observer = new IntersectionObserver(entries => {
        for (const entry of entries) {
            if (!entry.isIntersecting || !onScreen(entry.target)) continue;
            if (entry.target === loadMoreBlock.value) loadMore();
            if (entry.target === loadPreviousBlock.value) loadPrevious({auto: true});
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
                <div v-if="hasPrevious" ref="loadPreviousBlock" class="load-more load-more--previous">
                  <button class="btn btn-big btn-ghost" type="button" :disabled="loadingPrevious"
                          @click="loadPrevious">
                    {{ loadingPrevious ? $t('products.loading') : $t('storefront.grid.load_previous') }}
                  </button>
                </div>

                <div ref="gridTop" class="products-list">
                  <ProductCard v-for="product in products" :key="product.id" :product="product"
                               :type-name="typeNames[product.document_type] || ''"/>
                  <p v-if="!products.length" class="text black">{{ $t('storefront.grid.empty') }}</p>
                </div>

                <div v-if="hasNext" class="load-more">
                  <button class="btn btn-big btn-ghost" type="button" :disabled="loadingMore" @click="loadMore">
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
