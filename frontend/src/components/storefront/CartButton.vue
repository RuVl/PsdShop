<script setup>
import {computed} from 'vue';
import {useRoute} from 'vue-router';
import {storeToRefs} from 'pinia';
import IconCart from '@/components/icons/IconCart.vue';
import {useCartStore} from '@/stores/cart.js';

// The design's floating cart: a fixed round button bottom-right (`cartlequebutton` in
// style.css). The icon is our SVG component instead of the mockup's cart.png.
const route = useRoute();
const {cartItemCount} = storeToRefs(useCartStore());

const target = computed(() => ({name: 'cart', params: {lang: route.params.lang || 'en'}}));
</script>

<template>
  <router-link class="cartlequebutton" :to="target" :title="$t('routes.cart')" :aria-label="$t('routes.cart')">
    <IconCart size="small" class="floating-cart-icon"/>
    <span class="counter_cartlequebutton">{{ cartItemCount }}</span>
  </router-link>
</template>

<style>
/* style.css draws the icon as `#body .cartlequebutton::after` with cart.png - the file is gone,
   the SVG above replaces it. Same selector weight to win over the !important rule. */
#body .cartlequebutton::after {
  display: none !important;
}

#body .cartlequebutton .floating-cart-icon {
  color: #2136ff;
  margin-top: 3px;
}
</style>
