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
// Pages always on the row: the current one with a neighbour on each side, plus the first and the
// last. Same numbers as the bot page prints, so this follows Django's `get_elided_page_range` with
// the arguments storefront/views.py passes it.
const NEIGHBOURS = 1;
const PINNED_AT_EACH_END = 1;

// [from, to], inclusive; empty when `to` is the smaller one.
function range(from, to) {
    return Array.from({length: Math.max(0, to - from + 1)}, (_, index) => from + index);
}

const items = computed(() => {
    const total = props.totalPages;
    const current = props.page;
    // Short enough that eliding anything would save no slots.
    if (total <= (NEIGHBOURS + PINNED_AT_EACH_END) * 2) return range(1, total);

    const pages = [];

    // Up to the current page: the pinned first pages, a gap, then the neighbours. An ellipsis that
    // would hide a single page costs the slot it saves, so there the run is printed whole.
    if (current - NEIGHBOURS > PINNED_AT_EACH_END + 2) {
        pages.push(...range(1, PINNED_AT_EACH_END), ELLIPSIS, ...range(current - NEIGHBOURS, current));
    } else {
        pages.push(...range(1, current));
    }

    // After it, the same the other way round.
    if (current + NEIGHBOURS < total - PINNED_AT_EACH_END - 1) {
        pages.push(...range(current + 1, current + NEIGHBOURS), ELLIPSIS, ...range(total - PINNED_AT_EACH_END + 1, total));
    } else {
        pages.push(...range(current + 1, total));
    }

    return pages;
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
