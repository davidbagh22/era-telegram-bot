type Props = {
  size?: "small" | "large";
};

export function BrandLogo({ size = "small" }: Props) {
  return (
    <div className={`brand-logo brand-logo--${size}`} aria-label="ЭРА">
      <img src="/era-logo.png" alt="Логотип ЭРА" />
    </div>
  );
}
