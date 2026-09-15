#
# spec file for package matrix-mautrix-discord
#
# Copyright (c) 2026 Tomáš Čech
#
# All modifications and additions to the file contributed by third parties
# remain the property of their copyright owners, unless otherwise agreed
# upon. The license for this file, and modifications and additions to the
# file, is the same license as for the pristine package itself unless
# otherwise agreed upon.
#

%global bridge_user matrix-mautrix-discord
%global bridge_datadir %{_localstatedir}/lib/matrix-mautrix-discord
%global bridge_confdir %{_sysconfdir}/matrix-mautrix-discord
%global bridge_logdir %{_localstatedir}/log/matrix-mautrix-discord

Name:           matrix-mautrix-discord
Version:        0.7.7
Release:        0
Summary:        A Matrix-Discord puppeting bridge
License:        AGPL-3.0-only
Group:          Productivity/Networking/Chat
URL:            https://github.com/mautrix/discord
Source0:        https://github.com/mautrix/discord/archive/refs/tags/v%{version}.tar.gz#/mautrix-discord-%{version}.tar.gz
Source1:        %{name}.service
Source2:        %{name}.sysusers
Source3:        %{name}.tmpfiles
Source4:        vendor.tar.zst
# Security fixes:
# - gorilla/websocket 1.5.0 -> 1.5.3: GO-2026-6278 (CVSS 6.9), weak PRNG
#   (math/rand instead of crypto/rand) for WebSocket frame mask keys.
#   REACHABLE per govulncheck call-graph analysis via the remoteauth/
#   QR-login websocket flow (main.go -> bridge.Bridge.Main -> ... ->
#   websocket.Dialer.Dial, provisioning.go qrLogin -> websocket.Upgrader).
#   Unlike the telegram/whatsapp x/crypto findings, this one is a real,
#   exploitable vulnerability in this bridge, not just a vendored-but-
#   unused dependency.
# - golang.org/x/crypto 0.55.0 -> 0.56.0: GO-2026-6354 / GO-2026-6355
#   (SSH-client DoS, unreachable here — bridge has no SSH client).
# Audit performed with govulncheck 1.8.0 + osv-scanner 2.5.1, see
# audit/govulncheck-v0.7.7.txt and audit/osv-scanner-v0.7.7.txt in the
# packaging git repository for the full report.
Patch0:         0001-security-fixes-discord.patch
BuildRequires:  go1.27
BuildRequires:  olm-devel
BuildRequires:  sysuser-tools
BuildRequires:  zstd
BuildRequires:  gcc-c++
BuildRequires:  libstdc++-devel
%sysusers_requires
%systemd_requires
Requires:       libolm3
Requires:       %{name}-config = %{version}

%description
mautrix-discord is a Matrix-Discord puppeting bridge, allowing Matrix and
Discord users to talk to each other seamlessly, as if they were on the
same platform.

This package builds and runs the bridge as a native systemd service instead
of the upstream Docker container, under a dedicated unprivileged system
user, with configuration and persistent data kept in standard FHS
locations.

%package config
Summary:        Default configuration package for %{name}
Group:          Productivity/Networking/Chat
BuildArch:      noarch

%description config
Placeholder subpackage that owns %{_sysconfdir}/matrix-mautrix-discord so
the main package can depend on configuration being present without forcing
a specific config generator. The actual config.yaml/registration.yaml are
generated on first start by the bridge binary itself (see README).

%prep
%autosetup -p1 -n mautrix-discord-%{version} -a4

%build
export GOFLAGS="-mod=vendor -buildmode=pie"
export CGO_ENABLED=1
export GOPATH=%{_builddir}/go
go build -mod=vendor -ldflags="-linkmode=external" -o mautrix-discord .

%install
install -D -m 0755 mautrix-discord %{buildroot}%{_bindir}/matrix-mautrix-discord
install -D -m 0644 %{SOURCE1} %{buildroot}%{_unitdir}/%{name}.service
install -D -m 0644 %{SOURCE2} %{buildroot}%{_sysusersdir}/%{name}.conf
install -D -m 0644 %{SOURCE3} %{buildroot}%{_tmpfilesdir}/%{name}.conf
install -d -m 0750 %{buildroot}%{bridge_confdir}
install -d -m 0750 %{buildroot}%{bridge_datadir}
install -d -m 0750 %{buildroot}%{bridge_logdir}
install -D -m 0644 example-config.yaml %{buildroot}%{_datadir}/%{name}/example-config.yaml
%sysusers_generate_pre %{SOURCE2} %{bridge_user} %{name}.conf

%pre -f %{bridge_user}.pre
%service_add_pre %{name}.service

%post
%service_add_post %{name}.service
%tmpfiles_create %{_tmpfilesdir}/%{name}.conf

%preun
%service_del_preun %{name}.service

%postun
%service_del_postun %{name}.service

%files
%license LICENSE
%doc CHANGELOG.md
%{_bindir}/matrix-mautrix-discord
%{_unitdir}/%{name}.service
%{_sysusersdir}/%{name}.conf
%{_tmpfilesdir}/%{name}.conf
%dir %attr(0750,%{bridge_user},%{bridge_user}) %{bridge_datadir}
%dir %attr(0750,%{bridge_user},%{bridge_user}) %{bridge_logdir}
%dir %{_datadir}/%{name}
%{_datadir}/%{name}/example-config.yaml

%files config
%dir %attr(0750,%{bridge_user},%{bridge_user}) %{bridge_confdir}

%changelog
