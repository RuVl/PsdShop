<script setup>
import {ref} from 'vue';
import {sendPurchasesLinks} from '@/api/order.js';
import {useSettingsStore} from '@/stores/settings.js';
import {errorMessageKey} from '@/api/errors.js';
import PageDecor from '@/components/storefront/PageDecor.vue';

// The page you land on when the link from the e-mail is lost: it tops up anything undelivered,
// revokes the old purchases link and mails a fresh one (ADR-0002).
const email = ref('');
const sending = ref(false);
const error = ref(null);
const sentTo = ref('');

async function submit() {
    error.value = null;
    sending.value = true;
    try {
        await sendPurchasesLinks({email: email.value, language: useSettingsStore().currentLanguage});
        // Said here rather than by a redirect: the customer has to go to their inbox next, and a
        // bounce back to the catalog reads as if nothing happened.
        sentTo.value = email.value;
    } catch (e) {
        // 404 is "no paid orders on this address" and 502 is "the mail did not go out" - the
        // customer has to do something different in each case.
        error.value = errorMessageKey(e, {
            404: 'purchases.email.error.not_found',
            502: 'purchases.email.error.mail_failed',
        });
        console.error('Cannot send the purchases link:', e);
    } finally {
        sending.value = false;
    }
}
</script>

<template>
  <PageDecor/>

  <main class="main-content">
    <section class="shop mb-100">
      <div class="container">
        <h1 class="title-section black">{{ $t('routes.my_purchases') }}</h1>

        <p v-if="sentTo" class="text black">{{ $t('purchases.email.sent', {email: sentTo}) }}</p>

        <form v-else class="purchases-form" @submit.prevent="submit">
          <div class="input-box">
            <label class="input-box-label" for="purchases-email">{{ $t('purchases.email.ask') }}</label>
            <input id="purchases-email" v-model="email" class="input-box-input" type="email" name="email"
                   required autocomplete="email" :placeholder="$t('purchases.email.placeholder')">
          </div>

          <p v-if="error" class="text-small purchases-form__error">{{ $t(error) }}</p>

          <button class="button" type="submit" :disabled="sending">{{ $t('buttons.send_links') }}</button>
        </form>
      </div>
    </section>
  </main>
</template>

<style scoped>
.purchases-form {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 20px;
  max-width: 480px;
  margin-top: 25px;
}

.purchases-form .input-box {
  width: 100%;
}

.purchases-form__error {
  margin: 0;
  color: #f6294b;
}
</style>
