import { useAuth } from "../hooks/useAuth";
import { AdminLayout } from "../layouts/AdminLayout";
import { LeaderLayout } from "../layouts/LeaderLayout";
import { UserLayout } from "../layouts/UserLayout";
import { AuthErrorScreen } from "../screens/AuthErrorScreen";
import { BlockedScreen } from "../screens/BlockedScreen";
import { HomePlaceholder } from "../screens/HomePlaceholder";
import { PendingScreen } from "../screens/PendingScreen";

export function App() {
  const auth = useAuth();

  if (auth.status === "loading") {
    return null;
  }

  if (auth.status === "error") {
    return <AuthErrorScreen code={auth.code} detail={auth.detail} />;
  }

  const { user } = auth;

  if (user.application_status === "pending" || user.application_status === "needs_info") {
    return <PendingScreen />;
  }
  if (user.application_status === "rejected" || user.is_blocked) {
    return <BlockedScreen />;
  }

  const content = <HomePlaceholder user={user} />;
  if (user.is_admin) {
    return <AdminLayout>{content}</AdminLayout>;
  }
  if (user.is_leader) {
    return <LeaderLayout>{content}</LeaderLayout>;
  }
  return <UserLayout>{content}</UserLayout>;
}
