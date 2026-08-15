import { LegalPage, OperatorFact, Section } from "@/components/legal/LegalPage";
import { operator } from "@/lib/operator";

export const metadata = { title: "Terms — ShortPulse" };

export default function Terms() {
  return (
    <LegalPage title="Terms of service" updated="August 2026">
      <Section title="What this is">
        <p>
          ShortPulse turns a topic, or a video you upload, into a vertical video with a
          voiceover and word-synced captions. The software is open source under the MIT
          licence and can be run on your own machine for nothing. These terms cover the hosted
          service, where renders run on our hardware and are paid for with credits.
        </p>
      </Section>

      <Section title="Who you are contracting with">
        <p>
          The hosted service is provided by{" "}
          <strong className="text-white">
            <OperatorFact value={operator.name} missing="NEXT_PUBLIC_OPERATOR_NAME is unset" />
          </strong>
          , <OperatorFact value={operator.address} missing="NEXT_PUBLIC_OPERATOR_ADDRESS is unset" />
          {operator.taxId ? `, ${operator.taxId}` : ""}. Reach us at{" "}
          {operator.email ? (
            <a href={`mailto:${operator.email}`} className="underline underline-offset-2 hover:text-white">
              {operator.email}
            </a>
          ) : (
            <OperatorFact missing="NEXT_PUBLIC_OPERATOR_EMAIL is unset" />
          )}
          .
        </p>
        <p>
          These terms are governed by the law of{" "}
          <OperatorFact value={operator.country} missing="NEXT_PUBLIC_OPERATOR_COUNTRY is unset" />
          . If you are a consumer, this does not take away the protections of the law where you
          live, and you keep the right to bring a claim in your own courts.
        </p>
      </Section>

      <Section title="Credits">
        <p>
          Credits are bought in one-off packs. Nothing renews, nothing is billed on a
          schedule, and credits do not expire. The number of credits a render costs is shown
          before you start it and is taken from the same table the server charges from.
        </p>
        <p>
          If a render fails, the credits it cost are returned automatically. That is enforced
          in the ledger rather than done by hand, and a project can be refunded at most once.
        </p>
      </Section>

      <Section title="Withdrawal and refunds">
        <p>
          If you are a consumer in the EU, you normally have 14 days to withdraw from an
          online purchase. Credits are digital content delivered immediately, so at checkout
          you are asked to confirm that you want them available at once and that you
          understand this ends the withdrawal right for credits you go on to spend.
        </p>
        <p>
          <strong className="text-white">Unused credits can still be refunded within 14
          days.</strong> Ask, and the unspent balance is returned to the card that paid for
          it. Credits already spent on a completed render are not refundable — the compute
          they paid for has already happened.
        </p>
      </Section>

      <Section title="What you make">
        <p>
          Videos you generate are yours. There is no watermark, no licence back to us, and no
          restriction on commercial use. We claim nothing over your topics, scripts or
          uploads.
        </p>
        <p>
          Stock footage comes from Pexels and stays under the Pexels licence. The credits
          panel on each project lists the videographers, and Pexels&apos; terms require that
          attribution to be visible where you publish. Background music is &quot;Airport
          Lounge&quot; by Kevin MacLeod, CC BY 3.0, which also requires credit.
        </p>
      </Section>

      <Section title="What you upload">
        <p>
          You need the right to use whatever you upload. Do not upload material you do not
          hold the rights to, or content that is unlawful. Uploads are stored so the video can
          be re-rendered when you edit it, and are deleted with the project.
        </p>
      </Section>

      <Section title="What this does not promise">
        <p>
          Output quality varies with the topic and the visual mode, and the limitations are
          listed openly on the home page rather than buried here: diffusion draws extremities
          and on-screen text badly, stock footage is a closest match rather than a guarantee,
          and local language models sometimes under-deliver scenes. The service is provided as
          is.
        </p>
        <p>
          Renders are queued and run on shared hardware. There is no uptime guarantee and no
          promised turnaround time.
        </p>
      </Section>

      <Section title="Ending the account">
        <p>
          You can delete any project at any time, which removes its video and every file it
          produced. Ask and the account and everything in it will be deleted. Any unspent
          credits at that point are refundable under the terms above.
        </p>
      </Section>
    </LegalPage>
  );
}
