import { Link } from "react-router";
import { Layout } from "../components/Layout";

export function NotFoundPage() {
  return (
    <Layout>
      <div className="notice">
        <p>This page doesn't exist.</p>
        <Link to="/">Go to upload</Link>
      </div>
    </Layout>
  );
}
