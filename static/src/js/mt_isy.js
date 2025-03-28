// odoo.define('mt_isy.mt_isy', function (require) {
// "use strict";

// /**
//  * This module contains most of the basic (meaning: non relational) field
//  * widgets. Field widgets are supposed to be used in views inheriting from
//  * BasicView, so, they can work with the records obtained from a BasicModel.
//  */

// var basicFields = require('web.basic_fields');
// var AbstractField = require('web.AbstractField');
// var core = require('web.core');
// var qweb = core.qweb;
// var _t = core._t;


//     basicFields.FieldBinaryFile.include({
//         init: function () {
//             console.log('##################');
            
//             this._super.apply(this, arguments);
//             this.filename_value = this.recordData[this.attrs.filename];

//             this.max_upload_size = 5 * 1024 * 1024; // 5Mo            
           
//         },
//     });


//     var BasicController = require('web.BasicController');
//     var Dialog = require('web.Dialog');

//     BasicController.include({

//         _urgentSave(recordID) {
//             this.model.executeDirectly(() => {
//                 this.renderer.commitChanges(recordID);
//                 for (const key in this.pendingChanges) {
//                     const { changes, dataPointID, event } = this.pendingChanges[key];
//                     const options = {
//                         context: event.data.context,
//                         viewType: event.data.viewType,
//                         notifyChange: false,
//                     };
//                     this.model.notifyChanges(dataPointID, changes, options);
//                     this._confirmChange(dataPointID, Object.keys(changes), event);
//                 }
//                 if (this.isDirty()) {
//                     console.log('_urgentSave - isDirty');
//                     // this._saveRecord(recordID, { reload: false, stayInEdit: true });
//                 }
//             });
//         },

//         saveChanges: async function (recordId) {
//             // waits for _applyChanges to finish
//             console.log('saveChanges');
//             await this.mutex.getUnlockedDef();

//             recordId = recordId || this.handle;
//             // if (this.isDirty(recordId)) {
//             //     await this.savingDef;
//             //     await this.saveRecord(recordId, {
//             //         stayInEdit: true,
//             //         reload: false,
//             //     });
//             // }
//             if (this.isDirty(recordId)) {
//                 var self = this;
//                 var def = new Promise(function (resolve, reject) {
//                     var message = _t("The record has been modified, your changes will be discarded. Do you want to proceed?");
//                     var dialog = Dialog.confirm(self, message, {
//                         title: _t("Warning"),
//                         confirm_callback: resolve.bind(self, true),
//                         cancel_callback: reject,
//                     });
//                     dialog.on('closed', self, reject);
//                 });
//                 return def;
//             }
//         },
//     })
// });



