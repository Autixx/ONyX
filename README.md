Thats my fork for WGDashboard with couple of features - AWG2.0 support, easy-to-route connection destination (such 3x-ui has) and multihop with balancers support.
Original project: [https://wg.wgdashboard.dev/](https://wg.wgdashboard.dev/)

## Ubuntu 22.04 / 24.04 installer

Run on a clean VPS:

```bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/Autixx/WGD_AWG_fix_multihop.git
cd WGD_AWG_fix_multihop
sudo bash scripts/install_ubuntu.sh
```

Installer now auto-installs missing AWG components from official repos:
- `amneziawg-tools` (`awg`, `awg-quick`)
- `amneziawg-go`
- Node.js/npm (for frontend build)

If you want to skip that behavior, use:

```bash
sudo bash scripts/install_ubuntu.sh --no-install-awg --no-install-node --no-build-frontend
```

One-command deploy with ready inbound `wg0` (keys + NAT + interface up):

```bash
sudo bash scripts/install_ubuntu.sh --bootstrap-inbound wg0
```

Example for AWG inbound:

```bash
sudo bash scripts/install_ubuntu.sh --bootstrap-inbound awg0 --bootstrap-protocol awg --bootstrap-listen-port 51820
```

Custom AWG sources/refs are supported:

```bash
sudo bash scripts/install_ubuntu.sh \
  --awg-tools-repo https://github.com/amnezia-vpn/amneziawg-tools.git \
  --awg-tools-ref master \
  --awg-go-repo https://github.com/amnezia-vpn/amneziawg-go.git \
  --awg-go-ref master
```

AWG 2.0 bootstrap fields are supported (without legacy `I1..I5`).  
Supported keys: `Jc`, `Jmin`, `Jmax`, `S1`, `S2`, `S3`, `S4`, `H1`, `H2`, `H3`, `H4`.
If you do not pass `--awg-*` values, they are randomly generated for each new interface.

Example with explicit AWG 2.0 values:

```bash
sudo bash scripts/install_ubuntu.sh \
  --bootstrap-inbound awg0 \
  --bootstrap-protocol awg \
  --bootstrap-address 10.66.66.1/24 \
  --bootstrap-listen-port 51820 \
  --bootstrap-out-if ens3 \
  --awg-jc 4 --awg-jmin 40 --awg-jmax 70 \
  --awg-s1 20 --awg-s2 40 --awg-s3 80 --awg-s4 120 \
  --awg-h1 1 --awg-h2 2 --awg-h3 3 --awg-h4 4 \
  --bootstrap-force
```

After install:

```bash
systemctl status wg-dashboard.service --no-pager
journalctl -u wg-dashboard.service -f
```

## MultiHop GeoIP Direct (backend)

MultiHop supports GeoIP direct routing via `ipset`:
- `GeoDirectEnabled`: enable/disable GeoIP direct mode
- `GeoDirectCountries`: comma-separated ISO country codes (example: `ru,kz`)
- `GeoDirectSourceTemplate`: URL template with `{country}` placeholder  
  default: `https://www.ipdeny.com/ipblocks/data/aggregated/{country}-aggregated.zone`

When enabled, destination CIDRs for selected countries are loaded into `ipset` and traffic to them is kept on the main route (direct), while the rest follows MultiHop routing.
