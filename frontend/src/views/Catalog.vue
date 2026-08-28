<script setup>
import {computed, ref, watch} from 'vue';
import {useRoute, useRouter} from 'vue-router';
import CountrySidebar from '@/components/storefront/CountrySidebar.vue';
import ProductCard from '@/components/storefront/ProductCard.vue';
import IconSearch from '@/components/icons/IconSearch.vue';
import {fetchProducts} from '@/api/catalog.js';
import {useCatalogStore} from '@/stores/catalog.js';
import {useLocalized} from '@/composables/localized.js';

// The home page and every country/type listing - the SPA presentation of the same URLs the
// bot pages render (storefront/catalog.html). Markup per design/index.html.
const route = useRoute();
const router = useRouter();
const catalogStore = useCatalogStore();
const localized = useLocalized();

catalogStore.load();

const lang = computed(() => route.params.lang || 'en');
const countrySlug = computed(() => route.params.country || 'all');
const typeSlug = computed(() => route.params.type || 'all');

const selectedCountry = computed(() => catalogStore.countries.find(c => c.slug === countrySlug.value) || null);
const selectedType = computed(() => catalogStore.documentTypes.find(t => t.slug === typeSlug.value) || null);
const typeNames = computed(() => Object.fromEntries(catalogStore.documentTypes.map(t => [t.slug, localized(t)])));

// Grid state: loading, failed and empty must never look alike.
const products = ref([]);
const count = ref(0);
const page = ref(1);
const state = ref('loading');
const loadingMore = ref(false);
const notFound = ref(false);

const hasNext = computed(() => products.value.length < count.value);

async function loadPage(target, append = false) {
    if (append) loadingMore.value = true;
    else state.value = 'loading';
    try {
        const data = await fetchProducts({country: countrySlug.value, type: typeSlug.value, page: target});
        count.value = data.count;
        products.value = append ? [...products.value, ...data.results] : data.results;
        page.value = target;
        state.value = 'ready';
    } catch (error) {
        if (error.response?.status === 404) notFound.value = true;
        else state.value = 'failed';
    } finally {
        loadingMore.value = false;
    }
}

watch(
    () => [route.params.country, route.params.type],
    () => {
        notFound.value = false;
        products.value = [];
        loadPage(Number(route.query.page) || 1);
    },
    {immediate: true},
);

function loadMore() {
    const next = page.value + 1;
    // The URL keeps up so a reload or a shared link lands on the same page the bot would see.
    router.replace({query: {...route.query, page: next}});
    loadPage(next, true);
}

// The product search filters client-side, like the design's app.js did.
const productQuery = ref('');

const visibleProducts = computed(() => {
    const query = productQuery.value.trim().toLowerCase();
    if (!query) return products.value;
    return products.value.filter(product => localized(product).toLowerCase().includes(query));
});

function catalogTarget(country, type) {
    if (country === 'all' && type === 'all') return {name: 'home', params: {lang: lang.value}};
    return {name: 'catalog', params: {lang: lang.value, country, type}};
}
</script>

<template>
  <div class="bgs-header">
    <section class="home" id="home">
      <div class="container">
        <div class="home__body">
          <div class="home__block">
            <h1 class="home__title title white">{{ $t('storefront.hero.title') }}</h1>
            <p class="home__text text white">{{ $t('storefront.hero.text') }}</p>
          </div>
          <picture class="home__img"><img src="/static/storefront/img/home/home-img.png" alt="Decor"></picture>
        </div>
      </div>
    </section>
  </div>

  <main class="main-content">
    <div v-if="notFound" class="container">
      <p class="text black">{{ $t('storefront.grid.not_found') }}</p>
    </div>

    <section v-else class="shop mb-60">
      <div class="container">
        <form class="search" @submit.prevent>
          <label for="search-input" class="search__title text black">{{ $t('storefront.search.products') }}</label>
          <div class="search__wrap">
            <input v-model="productQuery" type="search" class="search__input" id="search-input"
                   :placeholder="$t('storefront.search.products_placeholder')">
            <IconSearch class="search-icon-svg"/>
          </div>
        </form>

        <div class="shop__body">
          <CountrySidebar :country-slug="countrySlug" :type-slug="typeSlug"/>

          <div class="shop__right-block">
            <div class="text black">{{ $t('storefront.grid.title') }}</div>
            <div class="products section">
              <h2 class="title-section title black">
                {{ selectedCountry ? localized(selectedCountry) : $t('storefront.grid.all_products') }}
                <template v-if="selectedType"> — {{ localized(selectedType) }}</template>
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
                        {{ localized(dtype) }}
                      </router-link>
                    </div>
                  </div>
                </div>
              </div>

              <p v-if="state === 'loading'" class="text black">{{ $t('products.loading') }}</p>
              <p v-else-if="state === 'failed'" class="text black">{{ $t('products.error') }}</p>
              <template v-else>
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
              </template>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section v-if="selectedCountry?.seo_text_en || selectedType?.seo_text_en" class="seo mb-60" id="seo">
      <div class="container">
        <div class="idesc">
          <p v-if="selectedCountry && localized(selectedCountry, 'seo_text')">{{ localized(selectedCountry, 'seo_text') }}</p>
          <p v-if="selectedType && localized(selectedType, 'seo_text')">{{ localized(selectedType, 'seo_text') }}</p>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped>
.search-icon-svg {
  position: absolute;
  right: 16px;
  top: 50%;
  transform: translateY(-50%);
  color: #2136ff;
  pointer-events: none;
}

.search__wrap {
  position: relative;
}

.load-more {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}
</style>
