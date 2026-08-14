"use client";

import { useEffect, useState } from "react";

import { getPublicPricing } from "@/lib/api";

/**
 * What a new account is granted, mirroring backend
 * `Settings.signup_credit_grant`.
 *
 * Used as the value until the server answers, and as the value forever if
 * it doesn't — a marketing page that renders a blank where a number goes
 * is worse than one quoting a stale number.
 */
export const SIGNUP_CREDITS = 5;

/**
 * The grant this deployment actually hands out.
 *
 * Server-driven rather than written into the copy, for a reason that had
 * already happened twice by the time this existed: the number was spelled
 * out in the landing stats, the hero sign-in card, the FAQ and the pricing
 * table, and `SIGNUP_CREDIT_GRANT` in a deployment's own .env overrides the
 * default all four were copied from. So the page can be wrong about the
 * offer it is making to the person reading it, in the direction of
 * promising credits that don't arrive.
 */
export function useSignupCredits(): number {
  const [credits, setCredits] = useState(SIGNUP_CREDITS);

  useEffect(() => {
    getPublicPricing()
      .then((pricing) => {
        if (pricing.signup_credits) setCredits(pricing.signup_credits);
      })
      .catch(() => {
        /* Keep the fallback. */
      });
  }, []);

  return credits;
}
