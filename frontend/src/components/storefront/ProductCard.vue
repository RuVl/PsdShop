<script setup>
import {computed} from 'vue';
import {useRoute, useRouter} from 'vue-router';
import IconCart from '@/components/icons/IconCart.vue';
import {useCartStore} from '@/stores/cart.js';
import {useLocalized} from '@/composables/localized.js';

// One grid card, markup per design/index.html. The document-type name comes with the product's
// type slug resolved against the loaded type list by the parent.
const props = defineProps({
    product: {type: Object, required: true},
    typeName: {type: String, default: ''},
});

const route = useRoute();
const router = useRouter();
const cart = useCartStore();
const localized = useLocalized();

const productRoute = computed(() => ({
    name: 'product',
    params: {
        lang: route.params.lang || 'en',
        country: props.product.country,
        type: props.product.document_type,
        productSlug: props.product.url_slug,
    },
}));

const inCart = computed(() => cart.inCart(props.product.id));

function addToCart() {
    cart.addItem(props.product);
}

function buyNow() {
    // Express checkout arrives with M3; until then "buy now" leads through the cart.
    cart.addItem(props.product);
    router.push({name: 'cart', params: {lang: route.params.lang || 'en'}});
}
</script>

<template>
  <div class="products-item" :data-card="product.document_type" :data-year="product.year || ''">
    <router-link class="product-item-image" :to="productRoute">
      <picture v-if="product.preview?.card">
        <source v-if="product.preview.card_webp" :srcset="product.preview.card_webp" type="image/webp">
        <img :src="product.preview.card" :alt="localized(product)">
      </picture>
    </router-link>
    <div class="product-item-content">
      <div class="product-item-badges">
        <div class="badge text-small primary">{{ typeName }}</div>
        <div v-if="product.year" class="badge-year text-small">{{ product.year }}</div>
      </div>
      <div class="product-item-title">
        <router-link :to="productRoute" class="product-item-title-link">{{ localized(product) }}</router-link>
      </div>
      <div class="product-item-prop-list">
        <div class="product-item-prop-label">{{ $t('storefront.card.price') }}</div>
        <div class="product-item-prop-content">$<span class="product-item-prop-value">{{ product.price }}</span></div>
      </div>
      <div class="product-item-controls">
        <button class="button" type="button" @click="buyNow">{{ $t('buttons.buy_now') }}</button>
        <button class="button button-cart" type="button" :disabled="inCart"
                :title="inCart ? $t('storefront.card.in_cart') : $t('buttons.add2cart')" @click="addToCart">
          <IconCart size="small"/>
        </button>
      </div>
    </div>
  </div>
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
