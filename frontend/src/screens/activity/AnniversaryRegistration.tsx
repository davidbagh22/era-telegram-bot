import { useRef, useState, type FormEvent } from "react";
import { ApiError, describeActionError, registerForAnniversary } from "../../api/client";
import { BottomSheet } from "../../components/BottomSheet";
import { successHaptic } from "../../telegram/webApp";
import type { AnniversaryRegistrationFields, EventItem } from "../../types/activity";

const CONSENT = "Подтверждая регистрацию, вы передаёте имя, фамилию, организацию и Telegram ID организаторам для учёта участников.";
const FIELDS = [
  { key: "first_name", label: "Имя", autoComplete: "given-name", maxLength: 80 },
  { key: "last_name", label: "Фамилия", autoComplete: "family-name", maxLength: 80 },
  { key: "organization", label: "Организация", autoComplete: "organization", maxLength: 160 },
] as const;
const EMPTY_FIELDS = { first_name: null, last_name: null, organization: null };

export function AnniversaryRegistration({ event }: { event: EventItem }) {
  const defaults = event.anniversary_defaults ?? EMPTY_FIELDS;
  const [registered, setRegistered] = useState(false);
  const [pending, setPending] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [fields, setFields] = useState<AnniversaryRegistrationFields>(defaults);
  const [error, setError] = useState("");
  const [closed, setClosed] = useState(false);
  const posting = useRef(false);
  const profileComplete = FIELDS.every(({ key }) => Boolean(defaults[key]));

  async function register(payload?: AnniversaryRegistrationFields) {
    if (posting.current) return;
    posting.current = true;
    setPending(true);
    setError("");
    try {
      const result = await registerForAnniversary(event.id, payload);
      if (!result.anniversary_registered) {
        setError("Регистрация не подтверждена. Попробуйте ещё раз.");
        return;
      }
      setRegistered(true);
      setFormOpen(false);
      successHaptic();
    } catch (reason) {
      if (reason instanceof ApiError && reason.message === "anniversary_profile_incomplete") {
        setFormOpen(true);
      } else {
        setError(describeActionError(reason));
        if (reason instanceof ApiError && ["anniversary_registration_closed", "anniversary_waitlisted", "event_not_found", "full"].includes(reason.message)) {
          setClosed(true);
          setFormOpen(false);
        }
      }
    } finally {
      posting.current = false;
      setPending(false);
    }
  }

  function start() {
    if (profileComplete) {
      void register();
    } else {
      setFormOpen(true);
    }
  }

  function submit(formEvent: FormEvent<HTMLFormElement>) {
    formEvent.preventDefault();
    void register(fields);
  }

  if (event.anniversary_registered || registered) {
    return <strong role="status" className="era-success-state">✓ Вы зарегистрированы</strong>;
  }

  if (!event.anniversary_registration_open || closed) {
    return <span role="status">{error || event.display_status}</span>;
  }

  return (
    <div style={{ display: "grid", gap: "0.35rem" }}>
      <button type="button" className="era-btn-primary" disabled={pending} onClick={start} style={{ width: "100%" }}>
        {pending ? "Сохраняем…" : "Зарегистрироваться"}
      </button>
      {profileComplete && (
        <small style={{ color: "var(--era-text-muted)" }}>{CONSENT}</small>
      )}
      {error && !formOpen && <span role="alert" style={{ color: "var(--era-error)" }}>{error}</span>}
      <BottomSheet open={formOpen} onClose={() => { if (!pending) setFormOpen(false); }} title="Регистрация на годовщину">
        <form onSubmit={submit} style={{ display: "grid", gap: "0.65rem", maxHeight: "66vh", overflowY: "auto" }}>
          {FIELDS.map(({ key, label, autoComplete, maxLength }) => (
            <label key={key} style={{ display: "grid", gap: "0.2rem" }}>
              {label}
              <input
                type="text" autoComplete={autoComplete} required maxLength={maxLength}
                placeholder={key === "organization" ? "Название или «Без организации»" : undefined}
                value={fields[key] ?? ""}
                onChange={(change) => setFields({ ...fields, [key]: change.target.value })}
              />
            </label>
          ))}
          <small style={{ color: "var(--era-text-muted)" }}>{CONSENT}</small>
          {error && <span role="alert" style={{ color: "var(--era-error)" }}>{error}</span>}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: "0.5rem" }}>
            <button type="button" disabled={pending} onClick={() => setFormOpen(false)}>Отмена</button>
            <button type="submit" className="era-btn-primary" disabled={pending}>
              {pending ? "Сохраняем…" : "Подтвердить"}
            </button>
          </div>
        </form>
      </BottomSheet>
    </div>
  );
}
