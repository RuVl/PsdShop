<script setup>
import {computed, onMounted, ref} from 'vue';
import {useRoute} from 'vue-router';
import {storeToRefs} from 'pinia';
import BuyModal from '@/components/storefront/BuyModal.vue';
import IconTrash from '@/components/icons/IconTrash.vue';
import {useCartStore} from '@/stores/cart.js';
import {useLocalized} from '@/composables/localized.js';

// The cart itself lives in localStorage (ADR-0010) - this page is its view, drawn with the
// design's storefront classes. A line is a catalog card payload: no quantities, USD only.
const route = useRoute();
const cartStore = useCartStore();
const {cartItems, cartItemCount, totalPrice} = storeToRefs(cartStore);
const localized = useLocalized();

const lang = computed(() => route.params.lang || 'en');

const state = ref('loading');
const dropped = ref(0);
const paying = ref(false);

// What the browser remembers can be months old, and the invoice is written from the catalog: a
// product taken off the shelf leaves the cart here rather than failing at the checkout, and a
// price that moved is corrected before the customer sees the total.
onMounted(async () => {
    const before = cartItemCount.value;
    try {
        await cartStore.refresh();
        dropped.value = before - cartItemCount.value;
        state.value = 'ready';
    } catch {
        state.value = 'failed';
    }
});
</script>

<template>
  <main class="main-content">
    <section class="shop mb-100">
      <div class="container">
        <h1 class="title-section black">{{ $t('cart_view.title') }}</h1>

        <p v-if="state === 'loading'" class="text black">{{ $t('cart_view.loading') }}</p>
        <p v-else-if="state === 'failed'" class="text black">{{ $t('cart_view.error') }}</p>

        <template v-else-if="cartItemCount">
          <p v-if="dropped" class="text-small cart__notice">{{ $t('cart_view.dropped') }}</p>

          <ul class="cart__list list-reset">
            <li v-for="item in cartItems" :key="item.id" class="cart__item">
              <router-link class="cart__preview"
                           :to="{name: 'product', params: {lang, country: item.country, type: item.document_type, productSlug: item.url_slug}}">
                <img v-if="item.preview?.card" :src="item.preview.card" :alt="localized(item)">
              </router-link>

              <div class="cart__body">
                <router-link class="cart__title text black"
                             :to="{name: 'product', params: {lang, country: item.country, type: item.document_type, productSlug: item.url_slug}}">
                  {{ localized(item) }}
                </router-link>
                <div class="cart__price text-small">
                  {{ $t('cart_view.cost') }}: <span class="primary">${{ Number(item.price).toFixed(2) }}</span>
                </div>
              </div>

              <button class="cart__remove" type="button" :title="$t('buttons.delete')"
                      @click="cartStore.removeItem(item.id)">
                <IconTrash/>
              </button>
            </li>
          </ul>

          <div class="cart__footer">
            <div class="cart__total text-mid black">
              {{ $t('cart_view.total') }}: <span class="primary">${{ totalPrice.toFixed(2) }}</span>
            </div>
            <button class="button" type="button" @click="paying = true">{{ $t('buttons.pay') }}</button>
          </div>
        </template>

        <div v-else class="cart__empty">
          <p class="text black">{{ $t('cart_view.empty') }}</p>
          <router-link class="button" :to="{name: 'home', params: {lang}}">{{ $t('buttons.to_catalog') }}</router-link>
        </div>
      </div>
    </section>

    <BuyModal v-model:open="paying"/>
  </main>
</template>

<style scoped>
.cart__notice {
  margin: 0 0 20px;
  color: #f6294b;
}

.cart__list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 25px 0 0;
  padding: 0;
}

/* The card of the mockup's basket row: white, soft shadow, 15px radius. */
.cart__item {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 15px 23px;
  background: #fff;
  border-radius: 15px;
  box-shadow: 0 0 81px 0 rgba(0, 0, 0, .1);
}

.cart__preview {
  flex: 0 0 auto;
  width: 72px;
  line-height: 0;
}

.cart__preview img {
  width: 100%;
  border-radius: 10px;
}

.cart__body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cart__title {
  color: #2c2045;
  overflow-wrap: anywhere;
  transition: color .3s ease;
}

.cart__title:hover {
  color: #6238f0;
}

.cart__price .primary {
  font-weight: 600;
}

.cart__remove {
  flex: 0 0 auto;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  color: #fff;
  background: #f6294b;
  border: 0;
  border-radius: 10px;
  cursor: pointer;
  transition: opacity .3s ease;
}

.cart__remove:hover {
  opacity: .7;
}

.cart__remove svg {
  width: 18px;
  height: 18px;
}

.cart__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 20px;
  margin-top: 30px;
}

.cart__total .primary {
  font-weight: 600;
}

.cart__empty {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 20px;
  margin-top: 25px;
}

@media (max-width: 560px) {
  .cart__item {
    flex-wrap: wrap;
    gap: 15px;
    padding: 15px;
  }

  .cart__footer {
    flex-direction: column;
    align-items: stretch;
  }

  .cart__footer .button {
    width: 100%;
  }
}
</style>
