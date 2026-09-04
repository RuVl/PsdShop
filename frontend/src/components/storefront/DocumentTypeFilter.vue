<script setup>
import {computed, nextTick, onBeforeUnmount, ref, watch} from 'vue';
import {useCatalogStore} from '@/stores/catalog.js';
import {useCatalogLinks} from '@/composables/useCatalogLinks.js';

// The document-type facet: chips that wrap, clamped to two rows, with a button when there is a
// third. style.css drew it as a row of 12px text links pushed to the right (`.filter-products
// -card-list`), which went ragged as soon as the shop had more than a handful of types.
//
// The bot page (storefront/catalog.html) renders the same chips out of the same list, uncollapsed
// - it has no script to expand them with, and every link has to be on the page anyway.
const props = defineProps({
    countrySlug: {type: String, default: 'all'},
    typeSlug: {type: String, default: 'all'},
});

const catalogStore = useCatalogStore();
const {catalogTarget} = useCatalogLinks();

function target(type) {
    return catalogTarget(props.countrySlug, type);
}

const grid = ref(null);
const collapsed = ref(true);
const overflowing = ref(false);

// Whether there is a third row to show. Measured rather than counted: a long type name takes a
// whole row of its own on a narrow screen, so "more than N chips" is not the same question.
function measure() {
    const box = grid.value;
    if (!box) return;
    // Only a collapsed box can be measured - expanded, it is exactly as tall as its content.
    overflowing.value = collapsed.value ? box.scrollHeight - box.clientHeight > 1 : true;
}

// The box changes height on a window resize, on a language switch and when the type list finally
// arrives; each of those changes the answer.
let observer = null;

watch(() => catalogStore.documentTypes, async () => {
    await nextTick();
    if (grid.value && typeof ResizeObserver !== 'undefined' && !observer) {
        observer = new ResizeObserver(measure);
        observer.observe(grid.value);
    }
    measure();
}, {immediate: true});

watch(collapsed, async () => {
    await nextTick();
    measure();
});

onBeforeUnmount(() => observer?.disconnect());

const typeCount = computed(() => catalogStore.documentTypes.length);
</script>

<template>
  <div class="filter-products">
    <div class="text-small black">{{ $t('storefront.filter.title') }}</div>

    <!-- The list is the whole control here, so a dead facets endpoint has to say so rather than
         render an empty row that reads as "this shop has one category". -->
    <p v-if="catalogStore.failed" class="text-small black">{{ $t('storefront.sidebar.failed') }}</p>

    <div v-else class="type-filter">
      <div ref="grid" class="type-filter__grid" :class="{'is-collapsed': collapsed}">
        <router-link class="type-chip" :class="{current: typeSlug === 'all'}" :to="target('all')">
          {{ $t('storefront.filter.all_categories') }}
        </router-link>
        <router-link v-for="dtype in catalogStore.documentTypes" :key="dtype.slug" class="type-chip"
                     :class="{current: dtype.slug === typeSlug}" :to="target(dtype.slug)">
          {{ dtype.name }}
        </router-link>
      </div>
      <button v-if="overflowing" type="button" class="btn-reset type-filter__toggle"
              :aria-expanded="!collapsed" @click="collapsed = !collapsed">
        {{ collapsed ? $t('storefront.filter.show_all', {count: typeCount}) : $t('storefront.filter.collapse') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
/* The chips and the grid live in storefront/css/shop.css: the bot page draws the same ones, and
   that file is the one both presentations link. Only the button is ours alone. */

.type-filter__toggle {
  align-self: center;
  padding: 4px 10px;
  font-size: 12px;
  line-height: normal;
  color: var(--primary);
  background: none;
  border: 0;
  cursor: pointer;
}

.type-filter__toggle:hover {
  text-decoration: underline;
}
</style>
