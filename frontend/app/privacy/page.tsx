import { LegalPage, Section } from "@/components/legal/LegalPage";

export const metadata = { title: "Privacy — ShortPulse" };

export default function Privacy() {
  return (
    <LegalPage title="Privacy" updated="August 2026">
      <Section title="What is stored">
        <p>
          Your email address, because that is how you sign in — there is no password to store.
          For each project: the topic or script you gave, the generated scene breakdown and
          caption timings, and the rendered video. If you uploaded a video, that file too.
          A ledger of credits bought, spent and refunded.
        </p>
        <p>
          No analytics, no tracking pixels, no advertising identifiers, no third-party scripts
          on the page.
        </p>
      </Section>

      <Section title="What leaves the server">
        <p>Only these, and only what each one needs:</p>
        <ul className="ml-4 flex list-disc flex-col gap-1.5">
          <li>
            <strong className="text-white">Supabase</strong> — sign-in and the database.
            Holds your email and your projects.
          </li>
          <li>
            <strong className="text-white">Stripe</strong> — payments. Card details go
            straight to Stripe and never reach this application.
          </li>
          <li>
            <strong className="text-white">Pexels</strong> — receives the search keywords for
            each scene when you use the stock footage mode. Not your topic, and nothing that
            identifies you.
          </li>
          <li>
            <strong className="text-white">OpenAI</strong> — receives the topic or script to
            write the scene breakdown from, on the hosted service. Self-hosted installs use a
            local model and send nothing.
          </li>
          <li>
            <strong className="text-white">Sentry</strong> — crash reports, if enabled.
            Configured not to include request contents.
          </li>
        </ul>
      </Section>

      <Section title="Voice and video">
        <p>
          Voiceovers are synthesised locally with Piper, and captions are timed locally with
          Whisper. Neither your script nor your uploaded video is sent to a speech service.
        </p>
      </Section>

      <Section title="How long">
        <p>
          Projects and their videos stay until you delete them. Deleting a project removes the
          video and every file it produced, not just the database row. Working files are
          discarded automatically as soon as a render finishes.
        </p>
        <p>
          The credit ledger is append-only and is kept for as long as the account exists,
          because it is also the record of what you paid.
        </p>
      </Section>

      <Section title="Your rights">
        <p>
          You can ask for a copy of your data, for it to be corrected, or for the account and
          everything in it to be deleted. Email the address in the repository and it will be
          done.
        </p>
      </Section>

      <Section title="Where it is">
        <p>
          Data is held in the EU. Stripe and OpenAI process some of it outside the EU under
          their own transfer safeguards.
        </p>
      </Section>
    </LegalPage>
  );
}
