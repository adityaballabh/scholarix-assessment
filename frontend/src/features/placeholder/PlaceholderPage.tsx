import styles from "./PlaceholderPage.module.css";

interface PlaceholderPageProps {
  section: string;
}

export default function PlaceholderPage({ section }: PlaceholderPageProps) {
  return (
    <section className={styles.placeholder}>
      <span className="sectionLabel">{section}</span>
    </section>
  );
}
