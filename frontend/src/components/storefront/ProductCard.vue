<script setup>
import {computed, ref} from 'vue';
import {useRoute} from 'vue-router';
import CheckoutModal from '@/components/storefront/CheckoutModal.vue';
import IconCart from '@/components/icons/IconCart.vue';
import {useCartStore} from '@/stores/cart.js';

// One grid card, markup per design/index.html. The document-type name comes with the product's
// type slug resolved against the loaded type list by the parent.
const props = defineProps({
    product: {type: Object, required: true},
    typeName: {type: String, default: ''},
});

const route = useRoute();
const cart = useCartStore();

const productRoute = computed(() => props.product.route(route.params.lang || 'en'));

const inCart = computed(() => cart.inCart(props.product.id));

function addToCart() {
    cart.addItem(props.product);
}

// Express checkout: one template, paid for without ever entering the cart.
const buying = ref(false);
</script>

<template>
  <div class="products-item" :data-card="product.document_type" :data-year="product.year || ''">
    <router-link class="product-item-image" :to="productRoute">
      <picture v-if="product.preview?.card">
        <source v-if="product.preview.card_webp" :srcset="product.preview.card_webp" type="image/webp">
        <img :src="product.preview.card" :alt="product.name">
      </picture>
    </router-link>
    <div class="product-item-content">
      <div class="product-item-badges">
        <div class="badge text-small primary">{{ typeName }}</div>
        <div v-if="product.year" class="badge-year text-small">{{ product.year }}</div>
      </div>
      <div class="product-item-title">
        <router-link :to="productRoute" class="product-item-title-link">{{ product.name }}</router-link>
      </div>
      <div class="product-item-prop-list">
        <div class="product-item-prop-label">{{ $t('storefront.card.price') }}</div>
        <div class="product-item-prop-content"><span class="product-item-prop-value">{{ product.priceLabel }}</span></div>
      </div>
      <div class="product-item-controls">
        <button class="button" type="button" @click="buying = true">{{ $t('buttons.buy_now') }}</button>
        <button class="button button-cart" type="button" :disabled="inCart"
                :title="inCart ? $t('storefront.card.in_cart') : $t('buttons.add2cart')" @click="addToCart">
          <IconCart size="small"/>
        </button>
      </div>
    </div>

    <CheckoutModal v-model:open="buying" :product="product"/>
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
