import { LegalPage, OperatorFact, Section } from "@/components/legal/LegalPage";
import { operator } from "@/lib/operator";

export const metadata = { title: "Privacy — ShortPulse" };

export default function Privacy() {
  return (
    <LegalPage title="Privacy" updated="September 2026">
      <Section title="What is stored">
        <p>
          Your email address, because that is how you sign in. If you sign in with Google, also
          the name and profile picture Google returns with it — see below. There is no password
          to store either way. For each project: the topic or script you gave, the generated scene breakdown and
          caption timings, and the rendered video. If you uploaded a video, that file too.
          A ledger of credits bought, spent and refunded.
        </p>
        <p>
          No analytics, no tracking pixels, no advertising identifiers, no third-party scripts
          on the page.
        </p>
      </Section>

      <Section title="Google user data">
        <p>
          ShortPulse receives data from Google in two places, and only when you start it.
        </p>
        <p>
          <strong className="text-white">Signing in with Google.</strong> Google returns your
          email address, your name and your profile picture (the <code>openid</code>,{" "}
          <code>email</code> and <code>profile</code> scopes). The email identifies your account
          and is where receipts go; the name and picture are shown only to you, in the app. None
          of it is used for anything else.
        </p>
        <p>
          <strong className="text-white">Connecting a YouTube channel.</strong> ShortPulse asks
          for one YouTube permission, <code>youtube.upload</code>, which lets it upload a video to
          your channel and nothing more — it cannot read your channel, your existing videos, your
          comments or your analytics. It is used for exactly one thing: uploading a video you
          made in ShortPulse, with the title and description you gave it, when you press
          Publish, or automatically after a render if you turned that on for the channel. Nothing
          is ever uploaded that you did not make and ask to publish.
        </p>

        <p className="mt-2 font-medium text-white">How it is used</p>
        <ul className="ml-4 flex list-disc flex-col gap-1.5">
          <li>To sign you in and keep your projects under your account.</li>
          <li>To upload the videos you choose to your YouTube channel.</li>
        </ul>
        <p>
          It is not used for advertising, not sold, not used to build profiles, and not used to
          train or improve any AI or machine-learning model — ours or anyone else&apos;s.
        </p>

        <p className="mt-2 font-medium text-white">Who it is shared with</p>
        <p>
          Nobody, beyond what is needed to provide the two features above. The videos you
          publish go to YouTube, which is Google. Your account record is stored with Supabase,
          the database provider named below, which processes it on ShortPulse&apos;s behalf and
          may not use it for anything else. Google user data is not transferred or disclosed to
          any other party, except where the law requires it.
        </p>

        <p className="mt-2 font-medium text-white">How it is protected</p>
        <ul className="ml-4 flex list-disc flex-col gap-1.5">
          <li>
            Every connection to ShortPulse, and from ShortPulse to Google, is encrypted in
            transit (HTTPS/TLS).
          </li>
          <li>
            The YouTube access and refresh tokens are encrypted before they are written to the
            database (Fernet: AES-128 with an HMAC, so a tampered token is rejected rather than
            used). The key is held in the server&apos;s environment, never in the database, so a
            copy of the database does not contain usable tokens.
          </li>
          <li>
            Tokens are never written to logs or sent to the browser, and only the server process
            that performs uploads can decrypt them.
          </li>
          <li>
            Access to the production database and server is limited to the operator named
            below.
          </li>
        </ul>

        <p className="mt-2 font-medium text-white">Keeping and deleting it</p>
        <p>
          Disconnecting a channel in ShortPulse deletes its stored tokens straight away; a record
          of which videos were published is kept so your library stays accurate. Deleting your
          account deletes your Google profile data, your connections and their tokens. You can
          also withdraw ShortPulse&apos;s access at any time from your Google Account, at{" "}
          <a
            href="https://myaccount.google.com/permissions"
            className="underline underline-offset-2 hover:text-white"
          >
            myaccount.google.com/permissions
          </a>
          .
        </p>

        <p>
          ShortPulse&apos;s use and transfer of information received from Google APIs adheres to
          the{" "}
          <a
            href="https://developers.google.com/terms/api-services-user-data-policy"
            className="underline underline-offset-2 hover:text-white"
          >
            Google API Services User Data Policy
          </a>
          , including the Limited Use requirements.
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
            <strong className="text-white">Replicate</strong> — receives one image prompt per
            scene, and returns the generated image, when you pick the AI-stills mode on the
            hosted service. Those prompts are written from your topic, so unlike the Pexels
            keywords above they usually describe what your video is about. Nothing that
            identifies you is sent with them. Self-hosted installs with a GPU generate the
            images on your own machine and send nothing.
          </li>
          <li>
            <strong className="text-white">YouTube, Instagram, Facebook and TikTok</strong> —
            receive a video, its title and its description when you publish to an account you
            connected, and nothing when you have not. Each connection&apos;s tokens are stored
            encrypted as described above.
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

      <Section title="Who is responsible">
        <p>
          This service is run by{" "}
          <strong className="text-white">
            <OperatorFact value={operator.name} missing="NEXT_PUBLIC_OPERATOR_NAME is unset" />
          </strong>
          , <OperatorFact value={operator.address} missing="NEXT_PUBLIC_OPERATOR_ADDRESS is unset" />
          {operator.taxId ? ` (${operator.taxId})` : ""}, who is the data controller for
          everything described here.
        </p>
        <p>
          Contact for anything on this page, including the requests below:{" "}
          {operator.email ? (
            <a href={`mailto:${operator.email}`} className="underline underline-offset-2 hover:text-white">
              {operator.email}
            </a>
          ) : (
            <OperatorFact missing="NEXT_PUBLIC_OPERATOR_EMAIL is unset" />
          )}
          .
        </p>
      </Section>

      <Section title="Your rights">
        <p>
          You can ask for a copy of your data, for it to be corrected, or for the account and
          everything in it to be deleted. Write to the address above and it will be done. If you
          think the law has been broken, you can also complain to your national data protection
          authority.
        </p>
      </Section>

      <Section title="Where it is">
        <p>
          Data is held in{" "}
          <OperatorFact
            value={operator.dataRegion}
            missing="NEXT_PUBLIC_OPERATOR_DATA_REGION is unset"
          />
          . Stripe, OpenAI and Replicate process some of it outside that region under their own
          transfer safeguards.
        </p>
      </Section>
    </LegalPage>
  );
}
