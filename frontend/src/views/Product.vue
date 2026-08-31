<script setup>
import {computed, nextTick, onBeforeUnmount, ref, watch} from 'vue';
import {useRoute} from 'vue-router';
import GLightbox from 'glightbox';
import 'glightbox/dist/css/glightbox.min.css';
import PageDecor from '@/components/storefront/PageDecor.vue';
import CheckoutModal from '@/components/storefront/CheckoutModal.vue';
import CountrySidebar from '@/components/storefront/CountrySidebar.vue';
import IconCart from '@/components/icons/IconCart.vue';
import {fetchProduct} from '@/api/catalog.js';
import {useCartStore} from '@/stores/cart.js';
import {useCatalogStore} from '@/stores/catalog.js';

// The product page per design/product.html: breadcrumbs, the shared sidebar, a gallery with
// a glightbox zoom, and the buy block. The `<id>-<slug>` URL segment resolves by the id.
const route = useRoute();
const cart = useCartStore();
const catalogStore = useCatalogStore();

catalogStore.load();

const lang = computed(() => route.params.lang || 'en');
const product = ref(null);
const state = ref('loading');

const productType = computed(() => catalogStore.documentTypes.find(t => t.slug === product.value?.document_type));
const productCountry = computed(() => catalogStore.countries.find(c => c.slug === product.value?.country));
const gallery = computed(() => (product.value?.images?.length ? product.value.images : []));
const mainImage = computed(() => gallery.value[0] || product.value?.preview || null);
const inCart = computed(() => product.value && cart.inCart(product.value.id));

let lightbox = null;

async function load() {
    state.value = 'loading';
    const id = Number.parseInt(route.params.productSlug, 10);
    try {
        product.value = await fetchProduct(id);
        state.value = 'ready';
        await nextTick();
        lightbox?.destroy();
        lightbox = GLightbox({selector: '.glightbox-product'});
    } catch (error) {
        state.value = error.response?.status === 404 ? 'not_found' : 'failed';
    }
}

watch(() => route.params.productSlug, load, {immediate: true});
onBeforeUnmount(() => lightbox?.destroy());

const listingTarget = computed(() => ({
    name: 'catalog',
    params: {lang: lang.value, country: route.params.country, type: route.params.type},
}));

function addToCart() {
    cart.addItem(product.value);
}

// Express checkout: one template, paid for without ever entering the cart.
const buying = ref(false);
</script>

<template>
  <PageDecor/>

  <main class="main-content">
    <div v-if="state === 'loading'" class="container">
      <p class="text black">{{ $t('products.loading') }}</p>
    </div>
    <div v-else-if="state === 'not_found'" class="container">
      <p class="text black">{{ $t('storefront.grid.not_found') }}</p>
    </div>
    <div v-else-if="state === 'failed'" class="container">
      <p class="text black">{{ $t('products.error') }}</p>
    </div>

    <template v-else>
      <div class="breadcrumbs">
        <div class="container">
          <ul class="list-reset">
            <li>
              <router-link :to="{name: 'home', params: {lang}}"><span>{{ $t('storefront.nav.home') }}</span></router-link>
            </li>
            <li>
              <router-link :to="listingTarget">
                <span>{{ productCountry ? productCountry.name : route.params.country }}<template v-if="productType"> — {{ productType.name }}</template></span>
              </router-link>
            </li>
            <li><span>{{ product.name }}</span></li>
          </ul>
        </div>
      </div>

      <section class="shop mb-100">
        <div class="container">
          <div class="shop__body">
            <CountrySidebar :country-slug="route.params.country" :type-slug="route.params.type"/>

            <div class="shop__right-block">
              <div class="text black">{{ $t('storefront.product.title') }}</div>
              <div class="product-item section">
                <div class="product-item__gallery">
                  <div v-if="mainImage" class="product-width-image">
                    <a :href="mainImage.page || mainImage.card" class="product-width-image-link glightbox-product">
                      <img :src="mainImage.card" :alt="product.name">
                    </a>
                  </div>
                  <div v-if="gallery.length > 1" class="product-width-images-list">
                    <a v-for="(image, index) in gallery.slice(1)" :key="index"
                       class="product-width-images-item glightbox-product" :href="image.page || image.card">
                      <img :src="image.card" :alt="product.name">
                    </a>
                  </div>
                </div>
                <div class="product-item__descr">
                  <div class="product-item__header">
                    <div class="product-item__header-props">
                      <div class="badge text-small primary">{{ productType ? productType.name : '' }}</div>
                      <div v-if="product.year" class="badge-year text-small">{{ product.year }}</div>
                    </div>
                    <span v-if="productCountry" class="product-item__lang">{{ productCountry.flag }}</span>
                  </div>
                  <h1 class="title-section black">{{ product.name }}</h1>
                  <div v-if="product.description" class="idesc product-item__text">
                    <p>{{ product.description }}</p>
                  </div>

                  <div class="product-item__info">
                    <div class="product-item__price">
                      <div class="text-mid black">{{ $t('storefront.card.price') }}</div>
                      <div class="text-mid black"><span class="primary">{{ product.priceLabel }}</span></div>
                    </div>
                    <div class="product-item__controls">
                      <button class="button" type="button" @click="buying = true">{{ $t('buttons.buy_now') }}</button>
                      <button class="button button-cart" type="button" :disabled="inCart"
                              :title="inCart ? $t('storefront.card.in_cart') : $t('buttons.add2cart')"
                              @click="addToCart">
                        <IconCart size="small"/>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <CheckoutModal v-model:open="buying" :product="product"/>
    </template>
  </main>
</template>

<style scoped>
/* The design drew this icon via a background PNG; the SVG inherits color instead. */
.button-cart {
  color: #2136ff;
}

.button-cart:disabled {
  opacity: .5;
  cursor: default;
}
</style>
