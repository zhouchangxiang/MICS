<template>
  <el-row>
    <el-col :span="24">
      <div class="navOptionsItem">
        <ul>
          <li v-for="item in navOptions" @click="showPage(item.value)"><a href="javascript:;" :class="{ active:item.value===navOptionsCurrent }" v-html="item.name"></a></li>
        </ul>
      </div>
      <Area v-if="navOptionsCurrent === 'Area'"></Area>
      <AreaTimeRange v-if="navOptionsCurrent === 'AreaTimeRange'"></AreaTimeRange>
      <PowerLoadRateRange v-if="navOptionsCurrent === 'PowerLoadRateRange'"></PowerLoadRateRange>
      <EnergyPrices v-if="navOptionsCurrent === 'EnergyPrices'"></EnergyPrices>
      <UnitConversion v-if="navOptionsCurrent === 'UnitConversion'"></UnitConversion>
      <UnitTable v-if="navOptionsCurrent === 'UnitTable'"></UnitTable>
      <EnergyLimit v-if="navOptionsCurrent === 'EnergyLimit'"></EnergyLimit>
      <EarlyWarningLimit v-if="navOptionsCurrent === 'EarlyWarningLimit'"></EarlyWarningLimit>
      <electricityBalance v-if="navOptionsCurrent === 'electricityBalance'"></electricityBalance>
      <TagDetail v-if="navOptionsCurrent === 'TagDetail'"></TagDetail>
    </el-col>
  </el-row>
</template>

<script>
  import SchedulingRules from '@/views/MaintainedTable/SchedulingRules'
  import Area from '@/views/MaintainedTable/Area'
  import AreaTimeRange from '@/views/MaintainedTable/AreaTimeRange'
  import PowerLoadRateRange from '@/views/MaintainedTable/PowerLoadRateRange'
  import EnergyPrices from '@/views/MaintainedTable/EnergyPrices'
  import UnitConversion from '@/views/MaintainedTable/UnitConversion'
  import UnitTable from '@/views/MaintainedTable/UnitTable'
  import EnergyLimit from '@/views/MaintainedTable/EnergyLimit'
  import EarlyWarningLimit from '@/views/MaintainedTable/EarlyWarningLimit'
  import electricityBalance from '@/views/MaintainedTable/electricityBalance'
  import TagDetail from '@/views/MaintainedTable/TagDetail'

  export default {
    name: "MaintainedBoard",
    components:{
      Area,AreaTimeRange,PowerLoadRateRange,EnergyPrices,UnitConversion,UnitTable,EnergyLimit,EarlyWarningLimit,electricityBalance,TagDetail
    },
    data(){
      return {
        navOptionsCurrent:'Area',
        navOptions:[
          {name:"区域管理",value:"Area"},
          {name:"区域时段范围",value:"AreaTimeRange"},
          {name:"额定功率",value:"PowerLoadRateRange"},
          {name:"能耗时段价格",value:"EnergyPrices"},
          {name:"能耗比例换算",value:"UnitConversion"},
          {name:"能耗单位",value:"UnitTable"},
          {name:"能耗限度",value:"EnergyLimit"},
          {name:"温度预警限度",value:"EarlyWarningLimit"},
          {name:"三项电流不平衡",value:"electricityBalance"},
          {name:"报表导出配置",value:"TagDetail"},
        ],
      }
    },
    methods: {
      showPage(index) {
        this.navOptionsCurrent = index
      }
    }
  }
</script>

<style scoped>

</style>
