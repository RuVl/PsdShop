<script setup>
import {computed, onMounted, ref} from 'vue';
import {useRoute} from 'vue-router';
import {fetchSubscription, unsubscribe as postUnsubscribe} from '@/api/order.js';
import PageDecor from '@/components/storefront/PageDecor.vue';

// Reached from a broadcast footer. Reading the token is a GET and changes nothing: opening the
// link out of curiosity - or having a mail scanner pre-fetch it - must not cost anyone the
// mailing list. The POST below is the only thing that opts out, and it takes a click.
const route = useRoute();
const token = route.params.token;

const lang = computed(() => route.params.lang || 'en');

const loading = ref(true);
const submitting = ref(false);
const invalid = ref(false);
const failed = ref(false);
// Whether the token was actually read. Without it a failed load would fall through to the
// "already unsubscribed" branch and tell the customer something that is not true.
const resolved = ref(false);
const email = ref('');
const subscribed = ref(false);
const done = ref(false);

async function resolveToken() {
    loading.value = true;
    failed.value = false;
    try {
        const data = await fetchSubscription(token);
        email.value = data.email;
        subscribed.value = data.is_subscribed;
        resolved.value = true;
    } catch (error) {
        if (error.response?.status === 400) invalid.value = true;
        else {
            failed.value = true;
            console.error('Error reading the unsubscribe link:', error);
        }
    } finally {
        loading.value = false;
    }
}

async function unsubscribe() {
    submitting.value = true;
    failed.value = false;
    try {
        const data = await postUnsubscribe(token);
        email.value = data.email;
        subscribed.value = false;
        done.value = true;
    } catch (error) {
        if (error.response?.status === 400) invalid.value = true;
        else {
            failed.value = true;
            console.error('Error unsubscribing:', error);
        }
    } finally {
        submitting.value = false;
    }
}

onMounted(resolveToken);
</script>

<template>
  <PageDecor/>

  <main class="main-content">
    <section class="shop mb-100">
      <div class="container">
        <h1 class="title-section black">{{ $t('routes.unsubscribe') }}</h1>

        <p v-if="loading" class="text black">{{ $t('unsubscribe.loading') }}</p>

        <div v-else-if="invalid" class="unsubscribe__state">
          <p class="text black">{{ $t('unsubscribe.invalid_link') }}</p>
          <router-link class="button" :to="{name: 'home', params: {lang}}">{{ $t('buttons.go_back_home') }}</router-link>
        </div>

        <div v-else-if="done" class="unsubscribe__state">
          <p class="text black">{{ $t('unsubscribe.done', {email}) }}</p>
          <router-link class="button" :to="{name: 'home', params: {lang}}">{{ $t('buttons.go_back_home') }}</router-link>
        </div>

        <div v-else-if="!resolved" class="unsubscribe__state">
          <p class="text unsubscribe__error">{{ $t('unsubscribe.unreachable') }}</p>
          <button class="button" type="button" @click="resolveToken">{{ $t('buttons.retry') }}</button>
        </div>

        <div v-else-if="!subscribed" class="unsubscribe__state">
          <p class="text black">{{ $t('unsubscribe.already', {email}) }}</p>
          <router-link class="button" :to="{name: 'home', params: {lang}}">{{ $t('buttons.go_back_home') }}</router-link>
        </div>

        <div v-else class="unsubscribe__state">
          <p class="text black">{{ $t('unsubscribe.confirm', {email}) }}</p>
          <p v-if="failed" class="text unsubscribe__error">{{ $t('unsubscribe.error') }}</p>
          <div class="unsubscribe__actions">
            <button class="button" type="button" :disabled="submitting" @click="unsubscribe">
              {{ submitting ? $t('unsubscribe.submitting') : $t('buttons.unsubscribe') }}
            </button>
            <router-link class="text-small unsubscribe__cancel" :to="{name: 'home', params: {lang}}">
              {{ $t('buttons.stay_subscribed') }}
            </router-link>
          </div>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped>
.unsubscribe__state {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 20px;
  margin-top: 25px;
}

.unsubscribe__error {
  font-weight: 600;
  color: #f6294b;
}

.unsubscribe__actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 25px;
}

.unsubscribe__cancel {
  color: #5f6779;
}

.unsubscribe__cancel:hover {
  opacity: .7;
}
</style>
