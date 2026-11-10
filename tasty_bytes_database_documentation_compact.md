# TASTY_BYTES — Compact Schema Reference

Snowflake database `TASTY_BYTES`. Fictional food-truck network (Snowflake demo dataset) operating across multiple countries; each truck can sell at two locations per day. The database covers Tasty Bytes sales from 2019-01-01 to 2022-11-01.

Format: `column | type | key | domain / notes`

> **Note:** ALL columns of every table are nullable. The `Nulls` marker below flags only columns that **actually contain** null values in the data.

> **Note:** When accessing the Tasty Bytes database directly in Snowflake, you may notice columns not listed here (e.g. `order_header.discount_id`, `order_header.order_channel`). They are omitted because their contents are entirely null. Ignore those columns.

---

## RAW_POS.COUNTRY — 30 rows
Grain: one row per city. Not referenced by any FK.

```
country_id      | NUMBER(18,0) | —  | 1, 2, 3 — repeats across rows
country         | VARCHAR      | —  | 'United States', 'Canada', 'England'
iso_currency    | VARCHAR(3)   | —  | 'USD', 'GBP', 'CAD' (ISO 4217)
iso_country     | VARCHAR(2)   | —  | 'US', 'GB', 'CA' (ISO 3166-1 alpha-2)
city_id         | NUMBER(19,0) | PK  | 10026, 10013
city            | VARCHAR      | - | 'Manchester', 'Toronto', 'London'
city_population | VARCHAR      | —  | '1010166', '978770' — stored as TEXT
```
- `city_population` is VARCHAR: cast with `TRY_TO_NUMBER()` before any numeric comparison, sort or aggregation.
- PK is documented as `city`; `city_id` is the more natural unique key for this grain.

## RAW_POS.FRANCHISE — 335 rows
Grain: one row per franchise owner. Referenced by `truck.franchise_id`.

```
franchise_id | NUMBER(38,0) | PK | 1, 2, 3
first_name   | VARCHAR      | —  | 'Andrew', 'Mary'
last_name    | VARCHAR      | —  | 'Johnson', 'Smith'
city         | VARCHAR      | —  | 'Boston', 'San Mateo', 'Denver'
country      | VARCHAR      | —  | 'United States', 'England', 'Canada'
e_mail       | VARCHAR      | —  | 'Annette.Gates@yahoo.com'
phone_number | VARCHAR      | —  | 'XXX-XXX-XXXX'
```

## RAW_POS.LOCATION — 13,093 rows
Grain: one row per physical selling location. Referenced by `order_header.location_id`.

```
placekey         | VARCHAR      | —  | '222-222@4hf-nch-k2k'
location_id      | NUMBER(19,0) | PK | 7379, 9132, 7251
location         | VARCHAR      | —  | 'Seasoners Fine Foods', 'Allens Bakery'
city             | VARCHAR      | —  | 'Denver', 'Manchester', 'Seattle'
region           | VARCHAR      | —  | NULLS. 'CO', 'Greater Manchester'
iso_country_code | VARCHAR      | —  | 'US', 'GB', 'CA'
country          | VARCHAR      | —  | 'United States', 'England', 'Canada'
```
- `region` format differs by country: 2-letter state codes for US rows, full names elsewhere. Do not assume a uniform format when filtering.

## RAW_POS.MENU — 100 rows
Grain: one row per menu item. Referenced by `order_detail.menu_item_id`. `menu_type_id` links conceptually to `truck.menu_type_id`.

```
menu_id                      | NUMBER(19,0) | —  | 10001, 10002
menu_type_id                 | NUMBER(38,0) | —  | 1, 2, 3
menu_type                    | VARCHAR      | —  | 'Ice Cream', 'BBQ', 'Tacos'
truck_brand_name             | VARCHAR      | —  | 'Freezing Point', 'Smoky BBQ'
menu_item_id                 | NUMBER(38,0) | PK | 10, 11, 12
menu_item_name               | VARCHAR      | —  | 'Lemonade', 'Sugar Cone'
item_category                | VARCHAR      | —  | 'Beverage','Dessert','Main','Snack'
item_subcategory             | VARCHAR      | —  | 'Cold Option','Hot Option','Warm Option'
cost_of_goods_usd            | NUMBER(38,4) | —  | USD per unit. 0.5–12
sale_price_usd               | NUMBER(38,4) | —  | USD per unit. 2–21
menu_item_health_metrics_obj | VARIANT      | —  | JSON, see below
```
- `menu_item_health_metrics_obj` shape:
  `{"menu_item_health_metrics":[{"ingredients":[...],"is_dairy_free_flag":"Y","is_gluten_free_flag":"Y","is_healthy_flag":"N","is_nut_free_flag":"Y"}],"menu_item_id":10}`
- Dietary flags are strings `'Y'`/`'N'`, not booleans. `menu_item_health_metrics` is an array → requires `LATERAL FLATTEN`. `ingredients` is a nested array → flatten again to search it.
```sql
SELECT menu_item_name
FROM menu, LATERAL FLATTEN(input => menu_item_health_metrics_obj:menu_item_health_metrics) f
WHERE f.value:is_gluten_free_flag::STRING = 'Y';
```
- Prices here are USD; `order_header.order_total` is in `order_header.order_currency`. Even though one would usually check and convert the currency, it has been confirmed that all the distinct values of `order_header.order_currency` are just 'USD', so no currency conversions are needed to be performed.

## RAW_POS.TRUCK — 450 rows
Grain: one row per food truck. `franchise_id` → `franchise.franchise_id`. Referenced by `order_header.truck_id`.

```
truck_id           | NUMBER(38,0) | PK | 1, 2, 3
menu_type_id       | NUMBER(38,0) | —  | 1, 2, 3
primary_city       | VARCHAR      | —  | 'Boston', 'Denver', 'New York City'
region             | VARCHAR      | —  | 'California', 'Colorado' — full names
iso_region         | VARCHAR      | —  | 'ON', 'NY', 'CO' — codes
country            | VARCHAR      | —  | 'United States', 'Canada'
iso_country_code   | VARCHAR      | —  | 'US', 'CA'
franchise_flag     | NUMBER(38,0) | —  | 0 = corporate-owned, 1 = franchised
year               | NUMBER(38,0) | —  | 2009, 2015 — truck MODEL year
make               | VARCHAR      | —  | 'Nissan', 'Freightliner', 'Chevrolet'
model              | VARCHAR      | —  | 'Van', 'Trailer', 'Step Van'
ev_flag            | NUMBER(38,0) | —  | 0 = non-electric, 1 = electric
franchise_id       | NUMBER(38,0) | FK → franchise.franchise_id | 1, 2, 3
truck_opening_date | DATE         | —  | 2019-01-01 — start of operations
```
- `year` is the vehicle model year, NOT a business/fiscal year. For anything time-related about operations use `truck_opening_date`.
- `truck.region` holds full names while `location.region` holds codes for US rows — the two are not comparable on region.

## RAW_POS.ORDER_HEADER — 248,201,269 rows
Grain: one row per order. Referenced by `order_detail.order_id`.

```
order_id         | NUMBER(38,0)     | PK | 360415976
truck_id         | NUMBER(38,0)     | FK → truck.truck_id | 322, 324
location_id      | FLOAT            | FK → location.location_id | 7379, 9132
customer_id      | NUMBER(38,0)     | FK → customer_loyalty.customer_id | NULLS
shift_id         | NUMBER(38,0)     | —  | 200358922
shift_start_time | TIME(9)          | —  | 08:00:00, 15:00:00
shift_end_time   | TIME(9)          | —  | 14:00:00, 22:00:00
order_ts         | TIMESTAMP_NTZ(9) | —  | 2021-08-22 13:28:22.000
order_currency   | VARCHAR(3)       | —  | 'USD'
order_total      | NUMBER(38,4)     | —  | 2.0–753.0, in order_currency
```
- `customer_id` is NULL for non-loyalty (anonymous) orders. INNER JOIN to `customer_loyalty` silently drops them — use LEFT JOIN unless the question is loyalty-only.
- `location_id` is FLOAT here but NUMBER(19,0) in `location`. Cast if precision issues appear.
- `order_ts` is TIMESTAMP_NTZ — no timezone. Orders from different countries are not comparable on absolute time.
- Very large table: always filter by date/truck/location and avoid unbounded scans.

## RAW_POS.ORDER_DETAIL — 673,655,465 rows
Grain: one row per line item within an order.

```
order_detail_id | NUMBER(38,0) | PK | 795179196
order_id        | NUMBER(38,0) | FK → order_header.order_id | 419309011
menu_item_id    | NUMBER(38,0) | FK → menu.menu_item_id | 71, 82, 132
line_number     | NUMBER(38,0) | —  | 0, 1, 2 — starts at 0
quantity        | NUMBER(5,0)  | —  | 1–22
unit_price      | NUMBER(38,4) | —  | 2.0–21.0
price           | NUMBER(38,4) | —  | 2.0–396.0 = quantity × unit_price
```
- **FAN-OUT:** joining `order_header` to `order_detail` multiplies header rows. Never `SUM(order_total)` after this join — aggregate `price` instead, or pre-aggregate `order_detail` in a CTE.
- Largest table in the database: always filter before aggregating.

## RAW_CUSTOMER.CUSTOMER_LOYALTY — 222,540 rows
Grain: one row per registered loyalty customer. Not all Tasty Bytes customers are registered here. Referenced by `order_header.customer_id`.

```
customer_id        | NUMBER(38,0) | PK | 1, 2, 3
first_name         | VARCHAR      | —  | NULLS. 'Rodolfo', 'Karla'
last_name          | VARCHAR      | —  | 'Tucker', 'Mullen'
city               | VARCHAR      | —  | 'Hamburg', 'Rio de Janeiro', 'Krakow'
country            | VARCHAR      | —  | 'Germany', 'Brazil', 'Poland'
postal_code        | VARCHAR      | —  | NULLS. Format varies by country
preferred_language | VARCHAR      | —  | 'German', 'Portuguese', 'Polish'
gender             | VARCHAR      | —  | 'Female', 'Male', 'Undisclosed'
marital_status     | VARCHAR      | —  | 'Single','Married','Divorced/Seperated','Undisclosed'
children_count     | VARCHAR      | —  | '0','1','2','Undisclosed' — stored as TEXT
sign_up_date       | DATE         | —  | 2019-02-19
birthday_date      | DATE         | —  | 1953-12-01
e_mail             | VARCHAR      | —  | 'Rodolfo.Tucker@ymail.com'
phone_number       | VARCHAR      | —  | 'XXX-XXX-XXXX'
```
- `children_count` is VARCHAR mixing digits with `'Undisclosed'`. Numeric aggregation requires `TRY_TO_NUMBER(children_count)`.
- `'Undisclosed'` is a real sentinel value in `gender`, `marital_status` and `children_count`, not a NULL — `IS NOT NULL` will not exclude it.
- `marital_status` contains the source-data misspelling `'Divorced/Seperated'`. Filters must match it exactly.
- `city`/`country` here are the customer's **residence**, not purchase geography. For where an order happened use `truck` or `location` via `order_header`.

---

# Views

Prefer these over raw joins when they answer the question.

## ANALYTICS.ORDERS_V
Wide denormalized order view. **Grain: one row per order line item** (built on `order_detail`).

Columns: `date` (DATE, derived from `order_ts`), `order_id`, `truck_id`, `order_ts`, `order_detail_id`, `line_number`, `truck_brand_name`, `menu_type`, `primary_city`, `region`, `country`, `franchise_flag`, `franchise_id`, `franchisee_first_name`, `franchisee_last_name`, `location_id`, `customer_id`, `children_count`, `gender`, `marital_status`, `menu_item_id`, `menu_item_name`, `cost_of_goods_usd,`, `quantity`, `unit_price`, `price`, `order_total`.

- **FAN-OUT:** `order_total` is the whole-order total repeated on every line. `SUM(order_total)` over this view overcounts revenue. Use `SUM(price)` for revenue, or `SUM(DISTINCT ...)`/a pre-aggregation by `order_id` when the order-level total is genuinely needed.
- `date` is the DATE cast of `order_ts`; use it for daily/monthly grouping.
- Customer columns come from a LEFT JOIN, so they are NULL for anonymous orders. All other joins are INNER, so rows require a matching truck, menu item, franchise and location.
- Built on the two largest tables — always filter by `date`, `country`, `truck_id` or similar.

## ANALYTICS.CUSTOMER_LOYALTY_METRICS_V
Per-loyalty-customer aggregates. **Grain: one row per customer** (only customers with at least one order; built with an INNER JOIN).

Columns: `customer_id`, `city`, `country`, `first_name`, `last_name`, `phone_number`, `e_mail`, `total_sales` (SUM of `order_header.order_total`), `visited_location_ids_array` (ARRAY of distinct `location_id`).

- `total_sales` is computed at order-header level, so it is NOT affected by line-item fan-out — it is a correct revenue figure per customer.
- `visited_location_ids_array` is an ARRAY: use `ARRAY_SIZE()` for a count of distinct locations visited, or `LATERAL FLATTEN` to expand it.
- `city`/`country` are the customer's residence, not purchase geography.

---

# Query conventions

- Fully qualify tables: `tasty_bytes.raw_pos.<table>`, `tasty_bytes.raw_customer.customer_loyalty`, `tasty_bytes.analytics.<view>`.
- Revenue = `SUM(price)` at line-item grain, or `SUM(order_total)` at order grain. Never mix the two.
- Profit per item = `sale_price_usd - cost_of_goods_usd` from `menu` (USD only).
- The `PUBLIC` and `INFORMATION_SCHEMA` schemas hold Snowflake defaults and load objects, not business data.
