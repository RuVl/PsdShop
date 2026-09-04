<script setup>
import {computed, nextTick, onBeforeUnmount, ref, watch} from 'vue';
import {useRoute, useRouter} from 'vue-router';
import CountrySidebar from '@/components/storefront/CountrySidebar.vue';
import Pagination from '@/components/storefront/Pagination.vue';
import ProductCard from '@/components/storefront/ProductCard.vue';
import CheckoutModal from '@/components/storefront/CheckoutModal.vue';
import Banner from '@/components/storefront/Banner.vue';
import DocumentTypeFilter from '@/components/storefront/DocumentTypeFilter.vue';
import IconCross from '@/components/icons/IconCross.vue';
import IconSearch from '@/components/icons/IconSearch.vue';
import {fetchProducts} from '@/api/catalog.js';
import {fetchPage} from '@/api/content.js';
import {useCatalogStore} from '@/stores/catalog.js';
import {useCatalogLinks} from '@/composables/useCatalogLinks.js';

// The home page and every country/type listing - the SPA presentation of the same URLs the
// bot pages render (storefront/catalog.html). Markup per design/index.html.
const route = useRoute();
const router = useRouter();
const catalogStore = useCatalogStore();

catalogStore.load();

const {lang, searchQuery, catalogTarget} = useCatalogLinks();
const countrySlug = computed(() => route.params.country || 'all');
const typeSlug = computed(() => route.params.type || 'all');

const isHome = computed(() => countrySlug.value === 'all' && typeSlug.value === 'all');
const isFiltered = computed(() => !isHome.value);

const selectedCountry = computed(() => catalogStore.countries.find(c => c.slug === countrySlug.value) || null);
const selectedType = computed(() => catalogStore.documentTypes.find(t => t.slug === typeSlug.value) || null);

// The owner-written SEO block of the front page (the `home` content.Page row). A failure is
// swallowed on purpose and this is the only place in the storefront where that is true: the block
// is decorative, it is absent on most listings anyway, and a row the owner never wrote 404s here -
// so "failed" and "empty" genuinely render the same thing.
const homePage = ref(null);
watch(isHome, async (home) => {
    if (home && !homePage.value) homePage.value = await fetchPage('home').catch(() => null);
}, {immediate: true});

// Grid state: loading, failed and empty must never look alike.
const products = ref([]);
const totalPages = ref(1);
const state = ref('loading');
const notFound = ref(false);
const grid = ref(null);

// One page on screen and that page in the address, the way the bot page has always worked.
// Infinite scroll used to hold a range of pages here; it cost a scroll anchor, two observers and
// a guess at the reader's direction, and it left `?page=` describing something other than what
// was on screen.
const page = computed(() => {
    // `?page=` is whatever the address bar carries: a word, a fraction or -3 all mean page one.
    const number = Number(route.query.page);
    return Number.isInteger(number) && number > 1 ? number : 1;
});

// What the grid is showing, as the API takes it. The search rides along with the facets: it is
// the server that filters, so the page count the pagination reads stays honest.
function facetParams() {
    return {country: countrySlug.value, type: typeSlug.value, q: searchQuery.value};
}

// Everything the grid loads from, in one string: an array getter would be a fresh object every
// run and refire the watcher on any route change.
function gridKey() {
    return `${countrySlug.value}/${typeSlug.value}/${searchQuery.value}/${page.value}`;
}

// The address of a page of this listing: everything else in the query stays, and page 1 carries
// no parameter at all - that is the canonical address of the listing.
function pageRoute(number) {
    const query = {...route.query};
    if (number > 1) query.page = String(number);
    else delete query.page;

    return {query};
}

// Which load is allowed to write to the grid. Two fast page clicks, or a debounced search landing
// on top of a facet link, leave two requests in flight; without this the slower one wins and the
// grid ends up showing something the address bar does not describe.
let latestLoad = 0;

async function load() {
    const token = ++latestLoad;
    state.value = 'loading';
    notFound.value = false;

    const facet = facetParams();
    const target = page.value;
    try {
        const data = await fetchProducts({...facet, page: target});
        if (token !== latestLoad) return;
        products.value = data.results;
        totalPages.value = data.totalPages;
        state.value = 'ready';
        await nextTick();
        scrollToGrid();
    } catch (error) {
        if (token !== latestLoad) return;
        if (error.response?.status !== 404) state.value = 'failed';
        // A 404 is either an unknown country/type slug or a page past the end of a real listing.
        else if (target === 1) notFound.value = true;
        else await landOnLastPage(facet, target, token);
    }
}

// Page 1 tells the two 404s apart: if it answers, the listing exists and the reader simply
// overshot - correct the address to the last real page, which loads it through the watcher.
async function landOnLastPage(facet, target, token) {
    try {
        const {totalPages: last} = await fetchProducts({...facet, page: 1});
        if (token !== latestLoad) return;
        // Same page number means the catalog grew between the two requests; there is nothing to
        // correct and no new address to reload from, so say the load failed rather than spin.
        if (last === target) state.value = 'failed';
        else router.replace(pageRoute(Math.max(1, last)));
    } catch (error) {
        if (token !== latestLoad) return;
        if (error.response?.status === 404) notFound.value = true;
        else state.value = 'failed';
    }
}

// A page change belongs at the cards, under the fixed header; landing on the page does not - the
// hero and the banner are part of what the reader came to. A new search stays where it is too:
// the field sits above the grid, and scrolling would pull it under the header mid-typing.
let shownPage = null;

function scrollToGrid() {
    const previous = shownPage;
    shownPage = page.value;
    if (previous === null || previous === page.value) return;

    const card = grid.value?.firstElementChild;
    if (!card) return;

    // `behavior: "instant"` on purpose: style.css puts `scroll-behavior: smooth` on <html>, and an
    // animated scroll both lands late and dies on the reader's first wheel.
    const header = document.querySelector('.header')?.getBoundingClientRect().height ?? 0;
    const top = Math.max(0, Math.round(window.scrollY + card.getBoundingClientRect().top - header - 16));
    window.scrollTo({top, behavior: 'instant'});
}

watch(() => gridKey(), load, {immediate: true});

// Express checkout: one modal for the whole grid, holding whichever card asked to buy.
const buyingProduct = ref(null);
const buyingOpen = computed({
    get: () => buyingProduct.value !== null,
    set: value => {
        if (!value) buyingProduct.value = null;
    },
});

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

// Without this the last keystroke fires up to 300ms after the reader has left the catalog, and
// `router.replace` rewrites the query of whatever route is open by then.
onBeforeUnmount(() => clearTimeout(searchTimer));

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
</script>

<template>
  <main class="main-content">
    <Banner v-if="isHome"/>

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

              <DocumentTypeFilter :country-slug="countrySlug" :type-slug="typeSlug"/>

              <p v-if="state === 'loading'" class="text black">{{ $t('products.loading') }}</p>
              <p v-else-if="state === 'failed'" class="text black">{{ $t('products.error') }}</p>
              <template v-else>
                <div ref="grid" class="products-list">
                  <ProductCard v-for="product in products" :key="product.id" :product="product"
                               :type-name="catalogStore.typeNameBySlug(product.document_type)"
                               @buy="buyingProduct = $event"/>
                  <p v-if="!products.length" class="text black">{{ $t('storefront.grid.empty') }}</p>
                </div>

                <Pagination :page="page" :total-pages="totalPages" :to="pageRoute"/>
              </template>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Gated on the localised getter, not on `seo_text_en`: a country written up in Russian only
         would otherwise show this block to a crawler on /ru/ and to nobody else - a divergence
         between the two presentations, which is what the bot template is judged against. -->
    <section v-if="selectedCountry?.seo_text || selectedType?.seo_text || (isHome && homePage)"
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

    <!-- One instance for the whole grid; the card that was clicked is what it holds. Mounted
         always, never behind a `v-if`: the modal arms its Escape handler and the scroll lock from
         a watcher on `open`, which never fires if the component appears already open. Its own
         markup is `v-if="open"`, so a closed one renders nothing. -->
    <CheckoutModal v-model:open="buyingOpen" :product="buyingProduct"/>
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
</style>
