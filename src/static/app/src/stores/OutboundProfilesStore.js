import {defineStore} from "pinia";
import {fetchGet, fetchPost} from "@/utilities/fetch.js";

export const OutboundProfilesStore = defineStore("OutboundProfilesStore", {
    state: () => ({
        Profiles: [],
        Settings: {
            Balancers: {
                Method: "random",
                Profiles: []
            },
            DNSSettings: {
                LocalDNSInstalled: false,
                LocalDNSAddress: ""
            },
            SiteToSite: {
                Enabled: false,
                NextProfile: ""
            },
            Multihop: {
                Profiles: []
            }
        },
        Loaded: false
    }),
    actions: {
        async getOutboundData() {
            await fetchGet("/api/getOutboundProfiles", {}, (res) => {
                if (res.status && res.data) {
                    this.Profiles = res.data.Profiles || []
                    this.Settings = res.data.Settings || this.Settings
                }
                this.Loaded = true
            })
        },
        async importProfile(data, callback = undefined) {
            await fetchPost("/api/importOutboundProfile", data, async (res) => {
                if (res.status) {
                    await this.getOutboundData()
                }
                if (callback) callback(res)
            })
        },
        async toggleProfile(name, callback = undefined) {
            await fetchPost("/api/toggleOutboundProfile", {Name: name}, async (res) => {
                if (res.status) {
                    await this.getOutboundData()
                }
                if (callback) callback(res)
            })
        },
        async deleteProfile(name, callback = undefined) {
            await fetchPost("/api/deleteOutboundProfile", {Name: name}, async (res) => {
                if (res.status) {
                    await this.getOutboundData()
                }
                if (callback) callback(res)
            })
        },
        async getProfileRaw(name, callback = undefined) {
            await fetchGet("/api/getOutboundProfileRawFile", {profileName: name}, (res) => {
                if (callback) callback(res)
            })
        },
        async updateProfileRaw(name, content, callback = undefined) {
            await fetchPost("/api/updateOutboundProfileRawFile", {
                Name: name,
                Content: content
            }, async (res) => {
                if (res.status) {
                    await this.getOutboundData()
                }
                if (callback) callback(res)
            })
        },
        async updateSettings(data, callback = undefined) {
            await fetchPost("/api/updateOutboundSettings", data, async (res) => {
                if (res.status) {
                    await this.getOutboundData()
                }
                if (callback) callback(res)
            })
        }
    }
})
