---
title: Rooms and Pricing
topic: rooms_pricing
source: Hotela dashboard screens + Hotela website (features, pricing) + kb/plans.json
source_urls:
  - https://hotelaapp.com/features
  - https://hotelaapp.com/pricing
last_updated: 2026-10-15
version: 2
audience: visitor
---

# Rooms and Pricing

## Room list and room categories

- Hotela lists every room with its room number, bed type and room category.
- Bed types include Single, Double, Twin Double and King size.
- Room categories let a hotel define its own types of room, such as Standard, Luxury, VIP or Deluxe.
- Each room category carries a cost and an occupancy range.
- Rooms and categories can be viewed per branch.
- Rooms are configured during setup.

## Room status and housekeeping

- Hotela Housekeeping lists dirty rooms with room number, category, bed type, status, checkout date and checkout time.
- Cleaning tasks can be assigned and tracked, and the live room status is visible to the team.
- Housekeeping has a second tab, Available Rooms, so the front desk can see which rooms are ready.
- The rooms that can be given to a guest are also listed on the Available Rooms tab of the reservations screen.

## Room rates

- Rates and availability are managed together with reservations from the reservation calendar.
- Rates also travel to the booking websites through the channel manager; the Bookings file holds that confirmed detail and what is not published.

## How Hotela prices its plans

- Plan names, prices, billing period and plan features live only in `plans.json`, which mirrors the public pricing page. Never quote a price that is not in `plans.json`.
- Prices are per branch, not per room. The pricing page states this for every plan.
- Plans are billed every six months. The pricing page also offers annual billing, but annual prices are not published, so annual pricing is not confirmed.
- The pricing page asks how many branches the business has, states that pricing is per branch, and says to contact Hotela after signup when more branches are needed. Each plan card reads "per branch · 1 branch · billed every 6 months".
- The price for the second and later branches is not published, and the exact branch limit per plan is not published.
- Every plan includes a 7-day free trial and free onboarding, and customers can cancel anytime; the full plan and trial terms are in the Policies file.

## Not confirmed for rooms and pricing

- Room type limits, room inventory limits and maintenance workflows.
- Room statuses beyond Dirty and Available.
- Room level pricing: rooms are not priced individually, plans are priced per branch.
- Any price for additional branches, annual prices, or discounts.
