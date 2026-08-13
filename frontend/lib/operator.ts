/**
 * Who runs this particular install.
 *
 * The legal pages describe what the software does — that part is the same
 * everywhere and lives in the pages themselves. Who is answerable for it
 * is not: it differs for every deployment, and GDPR requires the
 * controller's identity and a contact address to be published.
 *
 * Read from the environment rather than hardcoded, because this repository
 * is also what other people self-host. A name compiled into the source
 * would put whoever deployed it in the position of publishing someone
 * else's company as the data controller.
 *
 * Unset, the pages say so plainly instead of inventing a plausible
 * placeholder — an address nobody answers is worse than a stated gap, and
 * these values are compiled into the client bundle at build time, so a
 * missing one is a build that shipped without them.
 */
export interface Operator {
  /** Legal name of the person or company running the service. */
  name?: string;
  /** Registered address, one line. */
  address?: string;
  /** Where privacy requests and security reports actually arrive. */
  email?: string;
  /** VAT/company number, where one exists. */
  taxId?: string;
  /** Country whose law governs the terms, spelled out ("Poland"). */
  country?: string;
  /** Where the data physically sits, spelled out ("the EU (Frankfurt)").
   *  Stated rather than assumed: it is a claim that has to stay true when
   *  the database moves. */
  dataRegion?: string;
}

function clean(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

export const operator: Operator = {
  name: clean(process.env.NEXT_PUBLIC_OPERATOR_NAME),
  address: clean(process.env.NEXT_PUBLIC_OPERATOR_ADDRESS),
  email: clean(process.env.NEXT_PUBLIC_OPERATOR_EMAIL),
  taxId: clean(process.env.NEXT_PUBLIC_OPERATOR_TAX_ID),
  country: clean(process.env.NEXT_PUBLIC_OPERATOR_COUNTRY),
  dataRegion: clean(process.env.NEXT_PUBLIC_OPERATOR_DATA_REGION),
};

/** Whether this install has published who runs it. False on a self-hosted
 *  install that never filled these in — which is fine, nobody is selling
 *  anything there. */
export const operatorIsPublished = Boolean(operator.name && operator.email);
