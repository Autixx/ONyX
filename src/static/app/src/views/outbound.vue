<script>
import LocaleText from "@/components/text/localeText.vue";
import ProtocolBadge from "@/components/protocolBadge.vue";
import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import {OutboundProfilesStore} from "@/stores/OutboundProfilesStore.js";

export default {
    name: "outbound",
    components: {ProtocolBadge, LocaleText},
    setup() {
        const dashboardConfigurationStore = DashboardConfigurationStore();
        const outboundProfilesStore = OutboundProfilesStore();
        return {dashboardConfigurationStore, outboundProfilesStore}
    },
    data() {
        return {
            activeTab: "Multihop",
            tabs: ["Balancers", "DNS settings", "Site-to-site", "Multihop"],
            importForm: {
                Name: "",
                Protocol: "auto",
                Content: ""
            },
            balancerForm: {
                Method: "random",
                Profiles: []
            },
            dnsForm: {
                LocalDNSInstalled: false,
                LocalDNSAddress: ""
            },
            siteToSiteForm: {
                Enabled: false,
                NextProfile: ""
            },
            multihopFormProfiles: [],
            rawEditor: {
                Name: "",
                Content: "",
                Visible: false
            },
            profileActionLoading: {}
        }
    },
    computed: {
        allProfileNames() {
            return this.outboundProfilesStore.Profiles.map(x => x.Name)
        },
        multihopCandidates() {
            return this.outboundProfilesStore.Profiles
        },
        balancerCandidates() {
            const selected = this.outboundProfilesStore.Settings?.Multihop?.Profiles || []
            return this.outboundProfilesStore.Profiles.filter(x => selected.includes(x.Name))
        }
    },
    watch: {
        "outboundProfilesStore.Settings": {
            deep: true,
            handler() {
                this.syncForms()
            }
        }
    },
    async mounted() {
        await this.outboundProfilesStore.getOutboundData()
        this.syncForms()
    },
    methods: {
        syncForms() {
            const settings = this.outboundProfilesStore.Settings || {}
            this.balancerForm.Method = settings.Balancers?.Method || "random"
            this.balancerForm.Profiles = [...(settings.Balancers?.Profiles || [])]
            this.dnsForm.LocalDNSInstalled = Boolean(settings.DNSSettings?.LocalDNSInstalled)
            this.dnsForm.LocalDNSAddress = settings.DNSSettings?.LocalDNSAddress || ""
            this.siteToSiteForm.Enabled = Boolean(settings.SiteToSite?.Enabled)
            this.siteToSiteForm.NextProfile = settings.SiteToSite?.NextProfile || ""
            this.multihopFormProfiles = [...(settings.Multihop?.Profiles || [])]
        },
        message(content, type = undefined) {
            this.dashboardConfigurationStore.newMessage("Outbound", content, type)
        },
        availabilityClass(value) {
            if (value === "online") return "text-bg-success"
            if (value === "stale") return "text-bg-warning"
            if (value === "up") return "text-bg-info"
            return "text-bg-secondary"
        },
        formatHandshake(profile) {
            if (!profile.LatestHandshakeAt) {
                return "Never"
            }
            return profile.LatestHandshakeAt
        },
        formatGb(value) {
            if (!value || Number.isNaN(Number(value))) return "0.0000"
            return Number(value).toFixed(4)
        },
        async importProfile() {
            if (!this.importForm.Name || !this.importForm.Content) {
                this.message("Please provide profile name and content.", "warning")
                return
            }
            await this.outboundProfilesStore.importProfile({
                Name: this.importForm.Name,
                Protocol: this.importForm.Protocol,
                Content: this.importForm.Content
            }, (res) => {
                if (!res.status) {
                    this.message(res.message, "danger")
                    return
                }
                this.importForm.Name = ""
                this.importForm.Protocol = "auto"
                this.importForm.Content = ""
                this.message("Profile imported.")
            })
        },
        async toggleProfile(profile) {
            this.profileActionLoading[profile.Name] = true
            await this.outboundProfilesStore.toggleProfile(profile.Name, (res) => {
                if (!res.status) {
                    this.message(res.message, "danger")
                }
            })
            this.profileActionLoading[profile.Name] = false
        },
        async deleteProfile(profile) {
            if (!window.confirm(`Delete outbound profile "${profile.Name}"?`)) {
                return
            }
            this.profileActionLoading[profile.Name] = true
            await this.outboundProfilesStore.deleteProfile(profile.Name, (res) => {
                if (!res.status) {
                    this.message(res.message, "danger")
                    return
                }
                if (this.rawEditor.Name === profile.Name) {
                    this.rawEditor.Visible = false
                    this.rawEditor.Name = ""
                    this.rawEditor.Content = ""
                }
                this.message("Profile deleted.")
            })
            this.profileActionLoading[profile.Name] = false
        },
        async openRawEditor(name) {
            await this.outboundProfilesStore.getProfileRaw(name, (res) => {
                if (!res.status) {
                    this.message(res.message, "danger")
                    return
                }
                this.rawEditor.Name = name
                this.rawEditor.Content = res.data?.Content || ""
                this.rawEditor.Visible = true
            })
        },
        async saveRawEditor() {
            await this.outboundProfilesStore.updateProfileRaw(
                this.rawEditor.Name,
                this.rawEditor.Content,
                (res) => {
                    if (!res.status) {
                        this.message(res.message, "danger")
                        return
                    }
                    this.message("Profile updated.")
                }
            )
        },
        closeRawEditor() {
            this.rawEditor.Visible = false
            this.rawEditor.Name = ""
            this.rawEditor.Content = ""
        },
        async saveBalancers() {
            await this.outboundProfilesStore.updateSettings({
                Balancers: {
                    Method: this.balancerForm.Method,
                    Profiles: this.balancerForm.Profiles
                }
            }, (res) => {
                if (!res.status) {
                    this.message(res.message, "danger")
                    return
                }
                this.message("Balancer settings updated.")
            })
        },
        async saveDNSSettings() {
            await this.outboundProfilesStore.updateSettings({
                DNSSettings: {
                    LocalDNSInstalled: this.dnsForm.LocalDNSInstalled,
                    LocalDNSAddress: this.dnsForm.LocalDNSAddress
                }
            }, (res) => {
                if (!res.status) {
                    this.message(res.message, "danger")
                    return
                }
                this.message("DNS settings updated.")
            })
        },
        async saveSiteToSite() {
            await this.outboundProfilesStore.updateSettings({
                SiteToSite: {
                    Enabled: this.siteToSiteForm.Enabled,
                    NextProfile: this.siteToSiteForm.NextProfile
                }
            }, (res) => {
                if (!res.status) {
                    this.message(res.message, "danger")
                    return
                }
                this.message("Site-to-site settings updated.")
            })
        },
        async saveMultihop() {
            await this.outboundProfilesStore.updateSettings({
                Multihop: {
                    Profiles: this.multihopFormProfiles
                }
            }, (res) => {
                if (!res.status) {
                    this.message(res.message, "danger")
                    return
                }
                this.message("Multihop pool updated.")
            })
        }
    }
}
</script>

<template>
    <div class="mt-md-5 mt-3 text-body mb-3">
        <div class="container-md d-flex flex-column gap-3">
            <div class="d-flex align-items-center">
                <h2 class="mb-0">
                    <LocaleText t="Outbound"></LocaleText>
                </h2>
            </div>

            <div class="border-bottom pb-3">
                <ul class="nav nav-pills nav-justified align-items-center gap-2">
                    <li class="nav-item" v-for="t in this.tabs" :key="t">
                        <a
                            class="nav-link rounded-3"
                            role="button"
                            :class="{active: this.activeTab === t}"
                            @click="this.activeTab = t"
                        >
                            <h6 class="my-2">
                                <LocaleText :t="t"></LocaleText>
                            </h6>
                        </a>
                    </li>
                </ul>
            </div>

            <div v-if="this.activeTab === 'Balancers'" class="d-flex flex-column gap-3">
                <div class="card rounded-3 shadow-sm">
                    <div class="card-body d-flex flex-column gap-3">
                        <h5 class="mb-0">
                            <LocaleText t="Balancers"></LocaleText>
                        </h5>

                        <div>
                            <label class="form-label">
                                <LocaleText t="Method"></LocaleText>
                            </label>
                            <select class="form-select rounded-3" v-model="this.balancerForm.Method">
                                <option value="random">random</option>
                                <option value="leastload">leastload</option>
                                <option value="leastping">leastping</option>
                            </select>
                        </div>

                        <div>
                            <label class="form-label">
                                <LocaleText t="Profiles"></LocaleText>
                            </label>
                            <div class="d-flex flex-column gap-2">
                                <div class="form-check" v-for="p in this.balancerCandidates" :key="'balancer-' + p.Name">
                                    <input
                                        class="form-check-input"
                                        type="checkbox"
                                        :id="'balancer-profile-' + p.Name"
                                        :value="p.Name"
                                        v-model="this.balancerForm.Profiles"
                                    >
                                    <label class="form-check-label d-flex align-items-center gap-2"
                                           :for="'balancer-profile-' + p.Name">
                                        <samp>{{ p.Name }}</samp>
                                        <ProtocolBadge :mini="true" :protocol="p.Protocol"></ProtocolBadge>
                                    </label>
                                </div>
                                <small class="text-muted" v-if="this.balancerCandidates.length === 0">
                                    <LocaleText t="No multihop profiles selected yet. Select them in Multihop tab first."></LocaleText>
                                </small>
                            </div>
                        </div>

                        <div>
                            <button class="btn text-primary-emphasis bg-primary-subtle border-primary-subtle rounded-3"
                                    @click="saveBalancers">
                                <LocaleText t="Save"></LocaleText>
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <div v-else-if="this.activeTab === 'DNS settings'" class="d-flex flex-column gap-3">
                <div class="card rounded-3 shadow-sm">
                    <div class="card-body d-flex flex-column gap-3">
                        <h5 class="mb-0">
                            <LocaleText t="DNS settings"></LocaleText>
                        </h5>
                        <div class="form-check form-switch">
                            <input
                                class="form-check-input"
                                type="checkbox"
                                id="localDNSInstalled"
                                v-model="this.dnsForm.LocalDNSInstalled"
                            >
                            <label class="form-check-label" for="localDNSInstalled">
                                <LocaleText t="Local DNS Installed"></LocaleText>
                            </label>
                        </div>
                        <div>
                            <label class="form-label" for="localDNSAddress">
                                <LocaleText t="Local DNS Address"></LocaleText>
                            </label>
                            <input
                                id="localDNSAddress"
                                class="form-control rounded-3"
                                :disabled="!this.dnsForm.LocalDNSInstalled"
                                v-model="this.dnsForm.LocalDNSAddress"
                                placeholder="127.0.0.1"
                            >
                        </div>
                        <div>
                            <button class="btn text-primary-emphasis bg-primary-subtle border-primary-subtle rounded-3"
                                    @click="saveDNSSettings">
                                <LocaleText t="Save"></LocaleText>
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <div v-else-if="this.activeTab === 'Site-to-site'" class="d-flex flex-column gap-3">
                <div class="card rounded-3 shadow-sm">
                    <div class="card-body d-flex flex-column gap-3">
                        <h5 class="mb-0">
                            <LocaleText t="Site-to-site"></LocaleText>
                        </h5>
                        <div class="form-check form-switch">
                            <input
                                class="form-check-input"
                                type="checkbox"
                                id="siteToSiteEnabled"
                                v-model="this.siteToSiteForm.Enabled"
                            >
                            <label class="form-check-label" for="siteToSiteEnabled">
                                <LocaleText t="Enabled"></LocaleText>
                            </label>
                        </div>
                        <div>
                            <label class="form-label" for="siteToSiteProfile">
                                <LocaleText t="Next profile"></LocaleText>
                            </label>
                            <select
                                class="form-select rounded-3"
                                id="siteToSiteProfile"
                                :disabled="!this.siteToSiteForm.Enabled"
                                v-model="this.siteToSiteForm.NextProfile"
                            >
                                <option value="">
                                    <LocaleText t="Select profile"></LocaleText>
                                </option>
                                <option v-for="name in this.allProfileNames" :key="'s2s-' + name" :value="name">
                                    {{ name }}
                                </option>
                            </select>
                        </div>
                        <div>
                            <button class="btn text-primary-emphasis bg-primary-subtle border-primary-subtle rounded-3"
                                    @click="saveSiteToSite">
                                <LocaleText t="Save"></LocaleText>
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <div v-else class="d-flex flex-column gap-3">
                <div class="card rounded-3 shadow-sm">
                    <div class="card-body d-flex flex-column gap-3">
                        <h5 class="mb-0">
                            <LocaleText t="Import outbound profile"></LocaleText>
                        </h5>
                        <div class="row g-3">
                            <div class="col-12 col-lg-4">
                                <label class="form-label">
                                    <LocaleText t="Name"></LocaleText>
                                </label>
                                <input class="form-control rounded-3" v-model="this.importForm.Name" placeholder="awg1">
                            </div>
                            <div class="col-12 col-lg-4">
                                <label class="form-label">
                                    <LocaleText t="Protocol"></LocaleText>
                                </label>
                                <select class="form-select rounded-3" v-model="this.importForm.Protocol">
                                    <option value="auto">auto</option>
                                    <option value="wg">wg</option>
                                    <option value="awg">awg</option>
                                </select>
                            </div>
                            <div class="col-12">
                                <label class="form-label">
                                    <LocaleText t="Configuration File"></LocaleText>
                                </label>
                                <textarea
                                    class="form-control rounded-3"
                                    rows="8"
                                    v-model="this.importForm.Content"
                                    placeholder="[Interface]&#10;PrivateKey = ...&#10;Address = ...&#10;&#10;[Peer]&#10;PublicKey = ..."
                                ></textarea>
                            </div>
                        </div>
                        <div class="d-flex gap-2">
                            <button class="btn text-primary-emphasis bg-primary-subtle border-primary-subtle rounded-3"
                                    @click="importProfile">
                                <LocaleText t="Import"></LocaleText>
                            </button>
                            <button class="btn btn-outline-secondary rounded-3" @click="saveMultihop">
                                <LocaleText t="Save multihop pool"></LocaleText>
                            </button>
                        </div>
                    </div>
                </div>

                <div class="card rounded-3 shadow-sm">
                    <div class="card-body d-flex flex-column gap-3">
                        <div class="d-flex align-items-center">
                            <h5 class="mb-0">
                                <LocaleText t="Multihop profiles"></LocaleText>
                            </h5>
                        </div>
                        <p class="text-muted mb-0" v-if="this.outboundProfilesStore.Profiles.length === 0">
                            <LocaleText t="No outbound profiles yet."></LocaleText>
                        </p>

                        <div class="d-flex flex-column gap-3" v-else>
                            <div class="card rounded-3 border-0 bg-body-tertiary"
                                 v-for="p in this.outboundProfilesStore.Profiles"
                                 :key="'outbound-profile-' + p.Name">
                                <div class="card-body d-flex flex-column gap-3">
                                    <div class="d-flex flex-wrap align-items-center gap-2">
                                        <h6 class="mb-0 d-flex align-items-center gap-2">
                                            <span class="dot" :class="{active: p.Status}"></span>
                                            <samp>{{ p.Name }}</samp>
                                        </h6>
                                        <ProtocolBadge :protocol="p.Protocol" :mini="true"></ProtocolBadge>
                                        <span class="badge rounded-3 ms-auto" :class="availabilityClass(p.Availability)">
                                            {{ p.Availability }}
                                        </span>
                                    </div>

                                    <div class="row g-2">
                                        <small class="col-12 col-md-6 col-lg-3">
                                            <strong><LocaleText t="Latest Handshake"></LocaleText>:</strong>
                                            {{ formatHandshake(p) }}
                                        </small>
                                        <small class="col-6 col-lg-3">
                                            <strong><LocaleText t="Total Usage"></LocaleText>:</strong>
                                            {{ formatGb(p.DataUsage?.Total) }} GB
                                        </small>
                                        <small class="col-6 col-lg-3 text-primary-emphasis">
                                            <strong><LocaleText t="Total Received"></LocaleText>:</strong>
                                            {{ formatGb(p.DataUsage?.Receive) }} GB
                                        </small>
                                        <small class="col-6 col-lg-3 text-success-emphasis">
                                            <strong><LocaleText t="Total Sent"></LocaleText>:</strong>
                                            {{ formatGb(p.DataUsage?.Sent) }} GB
                                        </small>
                                    </div>

                                    <div class="row g-3">
                                        <div class="col-12 col-lg-5">
                                            <div class="form-check">
                                                <input
                                                    class="form-check-input"
                                                    type="checkbox"
                                                    :id="'multihop-member-' + p.Name"
                                                    :value="p.Name"
                                                    v-model="this.multihopFormProfiles"
                                                >
                                                <label class="form-check-label" :for="'multihop-member-' + p.Name">
                                                    <LocaleText t="Available for balancer"></LocaleText>
                                                </label>
                                            </div>
                                        </div>
                                        <div class="col-12 col-lg-7 d-flex flex-wrap gap-2 justify-content-lg-end">
                                            <button
                                                class="btn btn-outline-secondary rounded-3"
                                                :disabled="this.profileActionLoading[p.Name]"
                                                @click="openRawEditor(p.Name)">
                                                <LocaleText t="Edit Raw Configuration File"></LocaleText>
                                            </button>
                                            <button
                                                class="btn btn-outline-primary rounded-3"
                                                :disabled="this.profileActionLoading[p.Name]"
                                                @click="toggleProfile(p)">
                                                <LocaleText t="Toggle"></LocaleText>
                                            </button>
                                            <button
                                                class="btn btn-outline-danger rounded-3"
                                                :disabled="this.profileActionLoading[p.Name]"
                                                @click="deleteProfile(p)">
                                                <LocaleText t="Delete"></LocaleText>
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="card rounded-3 shadow-sm" v-if="this.rawEditor.Visible">
                    <div class="card-body d-flex flex-column gap-3">
                        <div class="d-flex align-items-center">
                            <h5 class="mb-0">
                                <LocaleText t="Edit Raw Configuration File"></LocaleText>:
                                <samp>{{ this.rawEditor.Name }}</samp>
                            </h5>
                        </div>
                        <textarea class="form-control rounded-3" rows="12" v-model="this.rawEditor.Content"></textarea>
                        <div class="d-flex gap-2">
                            <button class="btn text-primary-emphasis bg-primary-subtle border-primary-subtle rounded-3"
                                    @click="saveRawEditor">
                                <LocaleText t="Save"></LocaleText>
                            </button>
                            <button class="btn btn-outline-secondary rounded-3" @click="closeRawEditor">
                                <LocaleText t="Cancel"></LocaleText>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<style scoped>
.nav-link {
    cursor: pointer;
}
</style>
