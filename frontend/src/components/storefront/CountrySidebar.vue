<script setup>
import {computed, ref} from 'vue';
import {useRoute} from 'vue-router';
import {useCatalogStore} from '@/stores/catalog.js';

// The "store categories" sidebar per design/index.html - shared by the listing and the
// product page. Links keep the current document-type filter.
const props = defineProps({
    countrySlug: {type: String, default: 'all'},
    typeSlug: {type: String, default: 'all'},
});

const route = useRoute();
const catalogStore = useCatalogStore();

const lang = computed(() => route.params.lang || 'en');
const countryQuery = ref('');

const visibleCountries = computed(() => {
    const query = countryQuery.value.trim().toLowerCase();
    if (!query) return catalogStore.countries;
    return catalogStore.countries.filter(country => country.name.toLowerCase().includes(query));
});

// "All countries" is the way out of a selection, so it has to read as one of the rows: the same
// icon slot and the same count, which here is everything on the shelf.
const totalProducts = computed(() =>
    catalogStore.countries.reduce((sum, country) => sum + (country.products_count || 0), 0),
);

function target(country) {
    // The product search is carried over: picking a country narrows the same search.
    const query = route.query.q ? {q: route.query.q} : {};
    if (country === 'all' && props.typeSlug === 'all') return {name: 'home', params: {lang: lang.value}, query};
    return {name: 'catalog', params: {lang: lang.value, country, type: props.typeSlug}, query};
}
</script>

<template>
  <div class="shop__left-block">
    <div class="text black">{{ $t('storefront.sidebar.title') }}</div>
    <div class="categories section">
      <div v-if="catalogStore.popularCountries.length" class="categories__popular">
        <div class="categories__title">
          <picture class="categories__icon">
            <img src="/static/storefront/img/icons/popular.png" alt="">
          </picture>
          <div class="text-small black">{{ $t('storefront.sidebar.popular') }}</div>
        </div>
        <ul class="categories__list">
          <li v-for="country in catalogStore.popularCountries" :key="`popular-${country.slug}`"
              class="categories__item" :class="{current: country.slug === countrySlug}">
            <router-link :to="target(country.slug)">
              <span class="categories__item-icon">{{ country.flag }}</span>
              <span class="categories__item-title text black">{{ country.name }}</span>
              <span class="categories__item-count badge text-small primary">{{ country.products_count }}</span>
            </router-link>
          </li>
        </ul>
      </div>
      <div class="categories__all">
        <div class="text-small black">{{ $t('storefront.sidebar.all') }}</div>
        <div>
          <input v-model="countryQuery" type="text" class="categories__search text-mid black"
                 :placeholder="$t('storefront.search.country_placeholder')"
                 :aria-label="$t('storefront.search.country_placeholder')">
        </div>
        <ul class="categories__list">
          <li class="categories__item" :class="{current: countrySlug === 'all'}">
            <router-link :to="target('all')">
              <span class="categories__item-icon" aria-hidden="true">🌐</span>
              <span class="categories__item-title text black">{{ $t('storefront.sidebar.all_countries') }}</span>
              <span class="categories__item-count badge text-small primary">{{ totalProducts }}</span>
            </router-link>
          </li>
          <li v-for="country in visibleCountries" :key="country.slug"
              class="categories__item" :class="{current: country.slug === countrySlug}">
            <router-link :to="target(country.slug)">
              <span class="categories__item-icon">{{ country.flag }}</span>
              <span class="categories__item-title text black">{{ country.name }}</span>
              <span class="categories__item-count badge text-small primary">{{ country.products_count }}</span>
            </router-link>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* The design's rows carry a 23px flag image; ours is an emoji in a span, which inherits the body
   size and lines the rows up unevenly. */
.categories__item-icon {
  font-size: 20px;
  line-height: 1;
}

/* Which country is selected was invisible: `.current` is set here and in the filter chips, and
   style.css only styles it inside the design's own dropdown. Without this there is nothing to
   tell the reader they are filtered, and so nothing to suggest clearing it. */
.categories__item.current .categories__item-title {
  color: var(--primary);
}

.categories__item.current .categories__item-count {
  color: var(--white);
  background: var(--primary);
}
</style>
