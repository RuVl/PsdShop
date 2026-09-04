<script setup>
import {computed, onMounted, ref} from 'vue';
import {useRoute} from 'vue-router';
import {storeToRefs} from 'pinia';
import CheckoutModal from '@/components/storefront/CheckoutModal.vue';
import IconTrash from '@/components/icons/IconTrash.vue';
import {useCartStore} from '@/stores/cart.js';
import {useCatalogStore} from '@/stores/catalog.js';

// The cart itself lives in localStorage (docs/architecture.md) - this page is its view, drawn with the
// design's storefront classes. A line is a catalog card payload: no quantities, USD only.
const route = useRoute();
const cartStore = useCartStore();
const {cartItems, cartItemCount, totalPrice} = storeToRefs(cartStore);

// A card payload names its country and type by slug; the flag and the names live on the catalog
// rows, which is where the grid card reads them from too.
const catalogStore = useCatalogStore();
catalogStore.load();
// The line and its country row side by side: one lookup per line, not one per thing drawn from it.
const lines = computed(() => cartItems.value.map(item => ({item, country: catalogStore.countryBySlug(item.country)})));

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
            <li v-for="{item, country} in lines" :key="item.id" class="cart__item">
              <div class="cart__preview">
                <img v-if="item.preview?.card" :src="item.preview.card" :alt="item.name">
              </div>

              <div class="cart__body">
                <div class="cart__badges">
                  <span v-if="catalogStore.typeNameBySlug(item.document_type)" class="badge text-small primary">
                    {{ catalogStore.typeNameBySlug(item.document_type) }}
                  </span>
                  <span v-if="item.year" class="badge-year text-small">{{ item.year }}</span>
                </div>
                <!-- The whole row opens the product: this link is stretched over the card by
                     .cart__title::after, and the delete button is lifted above it. -->
                <router-link class="cart__title text black" :to="item.route(lang)">{{ item.name }}</router-link>
                <div v-if="country" class="cart__country text-small">
                  <span aria-hidden="true">{{ country.flag }}</span>
                  {{ country.name }}
                </div>
              </div>

              <div class="cart__prop">
                <div class="cart__prop-label text-small">{{ $t('cart_view.cost') }}</div>
                <div class="cart__prop-value primary">{{ item.priceLabel }}</div>
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
            <button class="btn btn-big btn-solid" type="button" @click="paying = true">{{ $t('buttons.pay') }}</button>
          </div>
        </template>

        <div v-else class="cart__empty">
          <p class="text black">{{ $t('cart_view.empty') }}</p>
          <router-link class="btn btn-big btn-ghost" :to="{name: 'home', params: {lang}}">
            {{ $t('buttons.to_catalog') }}
          </router-link>
        </div>
      </div>
    </section>

    <CheckoutModal v-model:open="paying"/>
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
  width: 100%;
  margin: 25px 0 0;
  padding: 0;
}

/* The card of the mockup's basket row: white, soft shadow, 15px radius. The columns are the ones
   a grid card has - picture, what it is, what it costs - so the eye reads the two the same way. */
.cart__item {
  position: relative;
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr) auto auto;
  grid-template-areas: 'preview body prop remove';
  align-items: center;
  gap: 20px;
  width: 100%;
  padding: 15px 23px;
  background: #fff;
  border-radius: 15px;
  box-shadow: 0 0 81px 0 rgba(0, 0, 0, .1);
  transition: box-shadow .3s ease;
}

.cart__item:hover {
  box-shadow: 0 0 40px 0 rgba(33, 54, 255, .18);
}

/* A fixed box, cropped like the grid card does it: uploads are not one shape, and a portrait
   scan used to stretch its row to three times the height of its neighbours. */
.cart__preview {
  grid-area: preview;
  width: 72px;
  height: 72px;
  overflow: hidden;
  border-radius: 10px;
  background: #eef1f8;
  line-height: 0;
}

.cart__preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.cart__body {
  grid-area: body;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.cart__badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.cart__title {
  color: #2c2045;
  font-weight: var(--bold);
  overflow-wrap: anywhere;
  transition: color .3s ease;
}

/* Stretched link: the row is the click target, so a customer can reopen the product from
   anywhere on the card. The delete button sits above it (z-index below). */
.cart__title::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 15px;
}

.cart__title:hover {
  color: #6238f0;
}

.cart__country {
  display: flex;
  align-items: center;
  gap: 6px;
  color: rgba(0, 0, 0, .5);
}

.cart__prop {
  grid-area: prop;
  text-align: right;
}

.cart__prop-label {
  color: rgba(0, 0, 0, .5);
}

.cart__prop-value {
  font-weight: var(--bold);
  white-space: nowrap;
}

.cart__remove {
  grid-area: remove;
  position: relative;
  z-index: 1;
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

/* On a phone the price moves under the name instead of squeezing the columns to nothing. */
@media (max-width: 560px) {
  .cart__item {
    grid-template-columns: 56px minmax(0, 1fr) auto;
    grid-template-areas:
      'preview body remove'
      'prop prop prop';
    /* The row is two lines tall here; a centred picture would float in the middle of them. */
    align-items: start;
    gap: 12px 15px;
    padding: 15px;
  }

  .cart__preview {
    width: 56px;
    height: 56px;
  }

  .cart__prop {
    display: flex;
    align-items: baseline;
    gap: 8px;
    text-align: left;
  }

  .cart__footer {
    flex-direction: column;
    align-items: stretch;
  }

  .cart__footer .btn {
    width: 100%;
  }
}
</style>
