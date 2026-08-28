<script setup>
import {computed, nextTick, onBeforeUnmount, ref, watch} from 'vue';
import IconCross from '@/components/icons/IconCross.vue';
import {useOrderStore} from '@/stores/order.js';
import {useCartStore} from '@/stores/cart.js';
import {useLocalized} from '@/composables/localized.js';
import {errorMessageKey} from '@/api/errors.js';

// The one place an order is paid for, in the design's modal markup (`.remodal.modalpay` and the
// `.modal-buy__*` block of design/style.css). Two modes, as in the mockup: `product` buys one
// template without touching the cart ("buy now"), `cart` buys everything the cart holds.
// remodal itself is not carried over - the open/close behaviour is this component.
const props = defineProps({
    // A catalog product payload for the express path; without it the whole cart is bought.
    product: {type: Object, default: null},
});

const open = defineModel('open', {default: false});

const orderStore = useOrderStore();
const cart = useCartStore();
const localized = useLocalized();

const email = ref('');
const sending = ref(false);
const error = ref(null);
const emailField = ref(null);

const mode = computed(() => (props.product ? 'product' : 'cart'));
const lines = computed(() => (props.product ? [props.product] : cart.cartItems));
const total = computed(() => lines.value.reduce((sum, line) => sum + Number(line.price), 0));

function close() {
    open.value = false;
}

async function submit() {
    error.value = null;
    sending.value = true;
    try {
        if (props.product) await orderStore.buyProduct(props.product, email.value);
        else await orderStore.buyCart(email.value);

        // Closed only on success: a refused checkout must not look like a working one.
        close();
    } catch (e) {
        // Plisio's own message is English-only and technical, so the customer gets our text and
        // the provider code goes to the console for us.
        error.value = errorMessageKey(e, {502: 'checkout.error.payment_gateway'});
        console.error('Checkout failed:', e.response?.data?.provider_code ?? '', e);
    } finally {
        sending.value = false;
    }
}

function onKeydown(event) {
    if (event.key === 'Escape') close();
}

// The page behind the modal must not scroll away under it, and the form is what the customer
// came for - so the e-mail field takes the focus.
watch(open, async (isOpen) => {
    document.documentElement.classList.toggle('remodal-is-locked', isOpen);
    if (isOpen) {
        error.value = null;
        window.addEventListener('keydown', onKeydown);
        await nextTick();
        emailField.value?.focus();
    } else {
        window.removeEventListener('keydown', onKeydown);
    }
});

onBeforeUnmount(() => {
    window.removeEventListener('keydown', onKeydown);
    document.documentElement.classList.remove('remodal-is-locked');
});
</script>

<template>
  <teleport to="body">
    <div v-if="open" class="remodal-overlay buy-modal-overlay" @click.self="close">
      <div class="remodal-wrapper buy-modal-wrapper" @click.self="close">
        <div class="remodal modalpay buy-modal" role="dialog" aria-modal="true"
             :data-modal-buy-method="mode">
          <button class="remodal-close buy-modal__close" type="button" :aria-label="$t('buttons.close')"
                  @click="close">
            <IconCross class="buy-modal__close-icon"/>
          </button>

          <div class="modal-buy__label">{{ $t('checkout.title') }}</div>

          <div class="modal-buy__props">
            <div v-for="line in lines" :key="line.id" class="modal-buy__props_item buy-modal__line">
              <span class="modal-buy__props_label">{{ localized(line) }}</span>
              <span class="modal-buy__props_value">${{ Number(line.price).toFixed(2) }}</span>
            </div>
            <p v-if="!lines.length" class="modal-buy__props_label">{{ $t('cart_view.empty') }}</p>
          </div>

          <form class="modal-buy__group" @submit.prevent="submit">
            <div class="modal-buy__checkout">
              <div class="modal-buy__checkout-group">
                <div class="input-box input-box--email">
                  <label class="input-box-label" for="checkout-email">{{ $t('checkout.email.ask') }}</label>
                  <input id="checkout-email" ref="emailField" v-model="email" class="input-box-input"
                         type="email" name="email" required autocomplete="email"
                         :placeholder="$t('checkout.email.placeholder')">
                </div>
              </div>
            </div>

            <p class="modal-buy__warning">{{ $t('checkout.delivery_notice') }}</p>

            <div class="modal-buy__shop">
              <div class="modal-buy__bottom">
                <div class="modal-buy__total">
                  <span class="modal-buy__total_label">{{ $t('checkout.total') }}</span>
                  <span class="modal-buy__total_value">${{ total.toFixed(2) }}</span>
                </div>
                <button class="button modal-buy__button-pay" type="submit"
                        :disabled="sending || !lines.length">
                  {{ sending ? $t('checkout.sending') : $t('buttons.pay') }}
                </button>
              </div>
              <p v-if="error" class="buy-modal__error">{{ $t(error) }}</p>
            </div>
          </form>
        </div>
      </div>
    </div>
  </teleport>
</template>

<style scoped>
/* The vendored remodal CSS hides all of these by default (it expects remodal.js to reveal them),
   so the layout the plugin used to apply lives here. */
.buy-modal-overlay {
  display: block;
  position: fixed;
  inset: 0;
  z-index: 9999;
}

.buy-modal-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  position: fixed;
  inset: 0;
  z-index: 10000;
  overflow: auto;
  padding: 20px 15px;
}

.buy-modal {
  display: block;
  width: 100%;
  margin: auto;
}

.buy-modal__close {
  display: flex;
  align-items: center;
  justify-content: center;
  /* The mockup's close button is a background PNG that was not carried over - the icon is ours. */
  background-image: none;
  background-color: #f6294b;
  border: 0;
  cursor: pointer;
}

.buy-modal__close-icon {
  width: 12px;
  height: 12px;
}

.buy-modal__line {
  width: 100%;
  flex-direction: row;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.buy-modal__error {
  margin: 14px 0 0;
  font-size: 12px;
  line-height: 1.38;
  color: #f6294b;
  text-align: left;
}
</style>
