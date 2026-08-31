# Domain vocabulary

The words below are the language of the domain, not table names. The storefront shows countries,
document types and years; the data model does not know what is drawn in the file, so the product
line can change without rewriting the schema. `not:` lists names to avoid.

Why the model looks the way it does: [`docs/architecture.md`](./docs/architecture.md).

## Catalog

- **Product** - a catalog entry: name, description, price, file, images, year. The thing that is
  bought. *not:* Item, Goods, Template.
- **Country** - the country of the document. Drives the sidebar with its counter and the flag on the
  card. *not:* Category, Group, Region.
- **DocumentType** - utility bill, bank statement, tax: the badge on the card and a filter.
  *not:* Category, Kind, Card.
- **ProductImage** - one image of a product; the first by position is the list preview, the rest are
  the gallery. *not:* Photo, Preview, Attachment.
- **Active** - the `Product` property that decides whether it is on the shelf. Removing a product
  means clearing the flag, never deleting: the file is still owed to whoever bought it.
  *not:* Published, Visible, Deleted.
- **Catalog facet** - a country x type pair where `all` means "any". One facet is one address
  (`/en/germany/utility-bill/`) and one sitemap entry; empty facets do not exist.
  *not:* Filter, Category, Section.

## Storefront

- **Shell** - the vite-built `index.html` with this page's meta injected by the server. A person
  gets it and the SPA takes over. *not:* Index, Template, Layout.
- **Bot page** - the full server-rendered HTML of the same address, for a crawler. Both
  presentations are built from one queryset and one meta; a divergence is a bug (it is cloaking).
  *not:* SSR, Prerender, Static.

## Selling

- **Customer** - a person identified by an e-mail address. Owns their orders, their subscription and
  the language their mail speaks. *not:* User, Client, Buyer, Account.
- **Buyer / lead** - a customer with a paid order, versus one who reached checkout and never paid.
  The difference lives in `CustomerQuerySet` and is defined by the `Order.paid_at` stamp.
  *not:* Active customer, Real customer.
- **Order** - the intent to buy a set of products, together with its payment state.
  *not:* Purchase, Cart, Checkout.
- **OrderItem** - an order line: one product at the price it had when bought. Also the unit of
  delivery: the token, its TTL and the download counter live here.
  *not:* LineItem, Position, DownloadLink.
- **Transaction** - a Plisio invoice. An order can have several: Plisio mints a new one when the
  buyer switches cryptocurrency. *not:* Payment, Invoice.

## Access

- **Purchases page** - where the customer sees every paid order and downloads the files. Opened by a
  token from the mail, without a password. *not:* Cabinet, Dashboard, Account page.
- **Access token** - the secret in a link. The `Customer` token opens the purchases page, the
  `OrderItem` token opens one file. Both expire. *not:* Key, UUID, Link.

## Broadcasts

- **Broadcast** - a message sent to every subscribed buyer. *not:* Newsletter, Campaign, Mailing.
- **BroadcastDelivery** - the fact that one `Broadcast` went to one `Customer`, with its result.
  This is what makes a run repeatable without duplicates. *not:* Send, Message, Recipient.
