<script setup>
import {computed} from 'vue';

// Numbered pages, the same set the bot page renders at the same addresses (ADR-0010). Real links,
// so a middle click opens a page in a tab and a crawler walks them.
const props = defineProps({
    page: {type: Number, required: true},
    totalPages: {type: Number, required: true},
    // Builds the route for a page number - the view owns what else the address carries (`?q=`).
    to: {type: Function, required: true},
});

const ELLIPSIS = '…';
// The window Django's paginator is asked for in storefront/views.py: both presentations must print
// the same numbers, so this is a port of `Paginator.get_elided_page_range`, not a second idea of
// what a page row looks like.
const ON_EACH_SIDE = 1;
const ON_ENDS = 1;

// [from, to], inclusive; empty when `to` is the smaller one.
function range(from, to) {
    return Array.from({length: Math.max(0, to - from + 1)}, (_, index) => from + index);
}

const items = computed(() => {
    const total = props.totalPages;
    const current = props.page;
    if (total <= (ON_EACH_SIDE + ON_ENDS) * 2) return range(1, total);

    // A gap is only worth an ellipsis when it hides more than the numbers it costs.
    const head = current > ON_EACH_SIDE + ON_ENDS + 2
        ? [...range(1, ON_ENDS), ELLIPSIS, ...range(current - ON_EACH_SIDE, current)]
        : range(1, current);
    const tail = current < total - ON_EACH_SIDE - ON_ENDS - 1
        ? [...range(current + 1, current + ON_EACH_SIDE), ELLIPSIS, ...range(total - ON_ENDS + 1, total)]
        : range(current + 1, total);

    return [...head, ...tail];
});
</script>

<template>
  <nav v-if="totalPages > 1" class="pagination" :aria-label="$t('pagination.label')">
    <router-link v-if="page > 1" class="btn btn-ghost pagination__step" :to="to(page - 1)"
                 :aria-label="$t('pagination.previous')" rel="prev">‹</router-link>

    <template v-for="(item, index) in items" :key="`${item}-${index}`">
      <span v-if="item === ELLIPSIS" class="pagination__gap" aria-hidden="true">{{ ELLIPSIS }}</span>
      <router-link v-else class="btn pagination__page" :class="item === page ? 'btn-solid' : 'btn-ghost'"
                   :to="to(item)" :aria-current="item === page ? 'page' : undefined">{{ item }}</router-link>
    </template>

    <router-link v-if="page < totalPages" class="btn btn-ghost pagination__step" :to="to(page + 1)"
                 :aria-label="$t('pagination.next')" rel="next">›</router-link>
  </nav>
</template>
