<template>
  <el-row>
    <el-col :span="24" style="background-color:#FFF;padding: 15px;margin-bottom: 15px;">
      <el-row>
        <el-col :span="24">
          <el-form :inline="true">
            <el-form-item>
              <el-select v-model="region" placeholder="请选择搜索字段" size="small">
                <el-option v-for="(item,index) in regionList" :label="item.label" :value="item.value" :key="index"></el-option>
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-input placeholder="请输入搜索内容" size="small" v-model="searchVal"></el-input>
            </el-form-item>
            <el-form-item>
              <el-button type="success" icon="el-icon-search" size="small" @click="searchTab">搜索</el-button>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" size="small" @click="openDialog('add')">添加</el-button>
            </el-form-item>
            <el-form-item>
              <el-button type="warning" size="small" @click="openDialog('edit')">修改</el-button>
            </el-form-item>
            <el-form-item>
              <el-button type="danger" size="small" @click="del">删除</el-button>
            </el-form-item>
          </el-form>
        </el-col>
      </el-row>
      <el-table :data="tableData" border tooltip-effect="dark" @selection-change="handleSelectionChange">
        <el-table-column type="selection"></el-table-column>
        <el-table-column prop="ID" label="ID"></el-table-column>
        <el-table-column prop="ProportionType" label="比例类型"></el-table-column>
        <el-table-column prop="Proportion" label="比例值"></el-table-column>
        <el-table-column prop="CreateDate" label="创建日期"></el-table-column>
      </el-table>
      <div class="paginationClass">
        <el-pagination background  layout="total, sizes, prev, pager, next, jumper"
                       :total="total"
                       :current-page="currentPage"
                       :page-sizes="[5,10,20]"
                       :page-size="pagesize"
                       @size-change="handleSizeChange"
                       @current-change="handleCurrentChange">
        </el-pagination>
      </div>
      <el-dialog :title="dialogTitle" :visible.sync="dialogVisible" :close-on-click-modal="false" width="40%">
        <el-form :model="submitForm" label-width="80px" :rules="rules" ref="ruleForm">
          <el-form-item label="ID">
            <el-input v-model="submitForm.ID" :disabled="true"></el-input>
          </el-form-item>
          <el-form-item label="比例类型" prop="ProportionType">
            <el-input v-model="submitForm.ProportionType"></el-input>
          </el-form-item>
          <el-form-item label="比例值" prop="Proportion">
            <el-input v-model="submitForm.Proportion"></el-input>
          </el-form-item>
        </el-form>
        <span slot="footer" class="dialog-footer">
          <el-button @click="dialogVisible = false">取 消</el-button>
          <el-button type="primary" @click="save('ruleForm')">保存</el-button>
        </span>
      </el-dialog>
    </el-col>
  </el-row>
</template>

<script>
  var moment = require('moment');
  export default {
    name: "UnitConversion",
    data(){
      return {
        tableData:[],
        total:0,
        pagesize:5,
        currentPage:1,
        multipleSelection: [],
        dialogVisible: false,
        submitForm:'',
        dialogTitle:'',
        rules:{
          ProportionType:[
            {required: true, message: '比例类型', trigger: 'blur'}
          ],
          Proportion:[
            {required: true, message: '比例值', trigger: 'blur'}
          ]
        },
        region:"",
        regionList:[
          {label:"比例类型",value:"ProportionType"}
        ],
        searchVal:""
      }
    },
    mounted() {
      this.getTableData()
    },
    methods:{
      getTableData(){
        this.axios.get("/api/CUID",{
          params: {
            tableName: "ElectricProportion",
            limit:this.pagesize,
            offset:this.currentPage - 1
          }
        }).then(res =>{
          var data = JSON.parse(res.data)
          this.tableData = data.rows
          this.total = data.total
        },res =>{
          console.log("请求错误")
        })
      },
      handleSizeChange(pagesize){ //每页条数切换
        this.pagesize = pagesize
        this.getTableData()
      },
      handleCurrentChange(currentPage) { // 页码切换
        this.currentPage = currentPage
        this.getTableData()
      },
      handleSelectionChange(val){  //选择行数
        this.multipleSelection = val;
      },
      searchTab(){
        this.axios.get("/api/CUID",{
          params: {
            tableName: "ElectricProportion",
            field:this.region,
            fieldvalue:this.searchVal,
            limit:this.pagesize,
            offset:this.currentPage - 1
          }
        }).then(res =>{
          var data = JSON.parse(res.data)
          this.tableData = data.rows
          this.total = data.total
        },res =>{
          console.log("请求错误")
        })
      },
      openDialog(val){
        this.dialogTitle = val
        if(val == "add"){
          this.dialogVisible = true
          this.submitForm = {
            ID:"",
            ProportionType:"",
            Proportion:"",
            CreateDate:moment().format("YYYY-MM-DD")
          }
        }else if(val == "edit"){
          if(this.multipleSelection.length == 1){
            this.dialogVisible = true
            let data = this.multipleSelection[0]
            this.submitForm = {
              ID:data.ID,
              ProportionType:data.ProportionType,
              Proportion:data.Proportion,
            }
          }else{
            this.$message({
              message: '请选择一条数据进行修改',
              type: 'warning'
            });
          }
        }
      },
      save(formName){
        this.$refs[formName].validate((valid) => {
          if (valid) {
            this.submitForm.tableName = "ElectricProportion"
            if(this.dialogTitle == "add"){
              this.axios.post("/api/CUID",this.qs.stringify(this.submitForm)).then(res =>{
                if(res.data == "OK"){
                  this.getTableData()
                }else{
                  this.$message({
                    type: 'info',
                    message: res.data
                  });
                }
                this.dialogVisible = false
              },res =>{
                console.log("请求错误")
              })
            }else if(this.dialogTitle == "edit"){
              this.axios.put("/api/CUID",this.qs.stringify(this.submitForm)).then(res =>{
                if(res.data == "OK"){
                  this.getTableData()
                }else{
                  this.$message({
                    type: 'info',
                    message: res.data
                  });
                }
                this.dialogVisible = false
              },res =>{
                console.log("请求错误")
              })
            }
          } else {
            return false;
          }
        });
      },
      del(){
        let mulId = []
        this.multipleSelection.forEach(item=>{
            mulId.push({id:item.ID});
        })
        if(this.multipleSelection.length >= 1){
          this.$confirm('确定删除所选记录？', '提示', {
            distinguishCancelAndClose:true,
            type: 'warning'
          }).then(()  => {
            this.axios.delete("/api/CUID",{
              params: {
                tableName: "ElectricProportion",
                delete_data: JSON.stringify(mulId)
              }
            }).then(res =>{
              if(res.data == "OK"){
                this.$message({
                  type: 'success',
                  message: '删除成功'
                });
              }
              this.getTableData()
            },res =>{
              console.log("请求错误")
            })
          }).catch(()   => {
            this.$message({
              type: 'info',
              message: '已取消删除'
            });
          });
        }else{
          this.$message({
            message: '至少选择一条数据进行删除',
            type: 'warning'
          });
        }
      }
    }
  }
</script>

<style scoped>

</style>
