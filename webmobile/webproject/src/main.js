import Vue from 'vue'
import App from './App'
import router from './router'

import store from './store/index'

Vue.config.productionTip = false

import './selfconfig/vantui'
import './selfconfig/vcharts'
import http from './selfconfig/http'
Vue.prototype.$http=http
import qs from 'qs'
Vue.prototype.$qs=qs

import './assets/css/base.css'

import 'lib-flexible/flexible'


/* eslint-disable no-new */
new Vue({
  el: '#app',
  router,
  store,
  components: { App },
  template: '<App/>'
})
