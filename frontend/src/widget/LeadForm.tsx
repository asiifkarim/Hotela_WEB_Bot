import { FormEvent, useState } from "react";

type Props = { apiUrl: string };

export function LeadForm({ apiUrl }: Props) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [consent, setConsent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!consent) {
      setError("Please check the consent box to continue.");
      return;
    }
    if (!email.trim() && !phone.trim()) {
      setError("Please provide either an email or phone number.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${apiUrl.replace(/\/$/, "")}/api/leads`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          email: email.trim() || undefined,
          phone: phone.trim() || undefined,
          consent,
        }),
      });

      if (!response.ok) {
        throw new Error("Unable to submit request. Please try again.");
      }
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submission failed.");
    } finally {
      setLoading(false);
    }
  }

  if (sent) {
    return (
      <div className="hotela-action-card hotela-lead-success">
        <div className="hotela-action-card-header">
          <strong>Thank you, {name}!</strong>
        </div>
        <p>A Hotela representative will follow up with you shortly.</p>
      </div>
    );
  }

  return (
    <form className="hotela-action-card hotela-lead-form" onSubmit={submit}>
      <div className="hotela-action-card-header">
        <strong>Request a Demo &amp; Follow-up</strong>
        <p>Leave your contact details and our team will get in touch.</p>
      </div>

      {error && <div className="hotela-form-error">{error}</div>}

      <div className="hotela-form-group">
        <label htmlFor="hotela-lead-name">Name *</label>
        <input
          id="hotela-lead-name"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Ali Khan"
          disabled={loading}
        />
      </div>

      <div className="hotela-form-group">
        <label htmlFor="hotela-lead-email">Email</label>
        <input
          id="hotela-lead-email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="name@company.com"
          disabled={loading}
        />
      </div>

      <div className="hotela-form-group">
        <label htmlFor="hotela-lead-phone">Phone / WhatsApp</label>
        <input
          id="hotela-lead-phone"
          type="tel"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="+92 300 1234567"
          disabled={loading}
        />
      </div>

      <label className="hotela-checkbox-label">
        <input
          type="checkbox"
          checked={consent}
          onChange={(e) => setConsent(e.target.checked)}
          disabled={loading}
        />
        <span>I consent to Hotela contacting me regarding products &amp; pricing.</span>
      </label>

      <button
        type="submit"
        className="hotela-form-submit"
        disabled={loading || !consent}
      >
        {loading ? "Sending..." : "Submit Request"}
      </button>
    </form>
  );
}
