<script setup>
import {computed, onMounted, ref} from 'vue';
import {useRoute} from 'vue-router';
import {useI18n} from 'vue-i18n';
import IconDownload from '@/components/icons/IconDownload.vue';
import IconRefresh from '@/components/icons/IconRefresh.vue';
import IconCopy from '@/components/icons/IconCopy.vue';
import {fetchPurchases, refreshAllPurchaseItems, refreshPurchaseItem} from '@/api/order.js';

// The page the delivery e-mail links to. The token in the URL is the whole authentication
// (docs/architecture.md), so a 404 from any call here means the link is spent - the page says so instead of
// retrying. Every line is one bought file with its own download link and TTL.
const route = useRoute();
const token = route.params.token;
const {locale} = useI18n();

const lang = computed(() => route.params.lang || 'en');

const state = ref('loading');
const email = ref('');
const orders = ref([]);
const copied = ref(null);

const items = computed(() => orders.value.flatMap(order => order.items));

function apply(fresh) {
    const target = items.value.find(item => item.id === fresh.id);
    if (target) Object.assign(target, fresh);
}

async function load() {
    state.value = 'loading';
    try {
        const data = await fetchPurchases(token);
        email.value = data.email;
        orders.value = data.orders;
        state.value = 'ready';
    } catch (error) {
        state.value = error.response?.status === 404 ? 'gone' : 'failed';
    }
}

async function withTokenGuard(request) {
    try {
        return await request();
    } catch (error) {
        if (error.response?.status === 404) state.value = 'gone';
        else console.error('Purchases page request failed:', error);
        return null;
    }
}

async function refresh(item) {
    const fresh = await withTokenGuard(() => refreshPurchaseItem(token, item.id));
    if (fresh) apply(fresh);
}

async function refreshAll() {
    const fresh = await withTokenGuard(() => refreshAllPurchaseItems(token));
    if (fresh) fresh.forEach(apply);
}

async function copyLink(item) {
    if (!item.download_url) return;

    try {
        await navigator.clipboard.writeText(item.download_url);
        copied.value = item.id;
        setTimeout(() => {
            if (copied.value === item.id) copied.value = null;
        }, 2000);
    } catch (error) {
        console.error('Error copying the link:', error);
    }
}

// "4 August 2026, 16:34" instead of the locale's raw numeric default.
function formatDate(value) {
    if (!value) return '';
    return new Date(value).toLocaleString(locale.value, {
        day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
}

onMounted(load);
</script>

<template>
  <main class="main-content">
    <section class="shop mb-100">
      <div class="container">
        <h1 class="title-section black">{{ $t('routes.my_purchases') }}</h1>

        <p v-if="state === 'loading'" class="text black">{{ $t('purchases.page.loading') }}</p>
        <p v-else-if="state === 'failed'" class="text black">{{ $t('purchases.page.error') }}</p>

        <div v-else-if="state === 'gone'" class="purchases__notice">
          <p class="text black">{{ $t('purchases.page.expired_link') }}</p>
          <router-link class="button" :to="{name: 'purchases', params: {lang}}">
            {{ $t('buttons.request_new_link') }}
          </router-link>
        </div>

        <p v-else-if="!orders.length" class="text black">{{ $t('purchases.page.empty') }}</p>

        <template v-else>
          <p class="text-small purchases__warning">{{ $t('purchases.page.share_warning') }}</p>

          <div class="purchases__head">
            <span class="text black">{{ email }}</span>
            <button class="button" type="button" @click="refreshAll">{{ $t('buttons.refresh_all_links') }}</button>
          </div>

          <div v-for="order in orders" :key="order.id" class="purchases__order">
            <div class="text-small purchases__order-title">
              {{ $t('purchases.page.order', {id: order.id, date: formatDate(order.paid_at || order.created_at)}) }}
            </div>

            <ul class="purchases__list list-reset">
              <li v-for="item in order.items" :key="item.id" class="purchases__item">
                <div class="purchases__body">
                  <span class="text black purchases__name">{{ item.product_name }}</span>
                  <span class="text-small">
                    ${{ Number(item.unit_price).toFixed(2) }}
                    <template v-if="item.is_downloadable">
                      · {{ $t('purchases.page.valid_until', {date: formatDate(item.expires_at)}) }}
                    </template>
                    <template v-else>
                      · <span class="purchases__expired">{{ $t('purchases.page.file_expired') }}</span>
                    </template>
                  </span>
                </div>

                <div class="purchases__actions">
                  <a v-if="item.is_downloadable" class="purchases__action" :href="item.download_url"
                     :title="$t('buttons.download')">
                    <IconDownload/>
                  </a>
                  <span v-else class="purchases__action is-disabled" :title="$t('purchases.page.file_expired')">
                    <IconDownload/>
                  </span>

                  <button class="purchases__action" type="button"
                          :class="{'is-copied': copied === item.id, 'is-disabled': !item.is_downloadable}"
                          :title="copied === item.id ? $t('buttons.copied') : $t('buttons.copy_link')"
                          @click="copyLink(item)">
                    <IconCopy/>
                  </button>

                  <button class="purchases__action" type="button" :title="$t('buttons.refresh_link')"
                          @click="refresh(item)">
                    <IconRefresh/>
                  </button>
                </div>
              </li>
            </ul>
          </div>
        </template>
      </div>
    </section>
  </main>
</template>

<style scoped>
.purchases__notice {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 20px;
}

.purchases__warning {
  margin: 0 0 20px;
  font-weight: 600;
  color: #f6294b;
}

.purchases__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 15px;
  margin-bottom: 25px;
}

.purchases__order + .purchases__order {
  margin-top: 30px;
}

.purchases__order-title {
  margin-bottom: 10px;
  color: #5f6779;
}

.purchases__list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 0;
}

.purchases__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 15px 23px;
  background: #fff;
  border-radius: 15px;
  box-shadow: 0 0 81px 0 rgba(0, 0, 0, .1);
}

.purchases__body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.purchases__name {
  overflow-wrap: anywhere;
}

.purchases__expired {
  color: #f6294b;
}

.purchases__actions {
  display: flex;
  align-items: center;
  gap: 18px;
  flex: 0 0 auto;
}

.purchases__action {
  display: flex;
  padding: 0;
  color: #2136ff;
  background: none;
  border: 0;
  line-height: 0;
  cursor: pointer;
  transition: opacity .3s ease, color .3s ease;
}

.purchases__action:hover {
  opacity: .7;
}

.purchases__action svg {
  width: 22px;
  height: 22px;
}

.purchases__action.is-disabled {
  color: #9a9aa5;
  pointer-events: none;
}

/* A momentary confirmation for a button whose only label is its tooltip. */
.purchases__action.is-copied {
  color: #12a150;
}

@media (max-width: 560px) {
  .purchases__item {
    flex-direction: column;
    align-items: flex-start;
    padding: 15px;
  }
}
</style>
