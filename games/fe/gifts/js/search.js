(function($) {
    $.fn.fixDiv = function(options) {
        var defaultVal = {
            top: 10
        };
        var obj = $.extend(defaultVal, options);
        $this = this;
        var _top = $this.offset().top;
        var _left = $this.offset().left;
        $(window).scroll(function() {
            var _currentTop = $this.offset().top;
            var _scrollTop = $(document).scrollTop();
            if (_scrollTop > _top) {
                $this.offset({
                    top: _scrollTop + obj.top,
                    left: _left
                });
            } else {
                $this.offset({
                    top: _top,
                    left: _left
                });
            }
        });
        return $this;
    };
})(jQuery);

$(function(){
    $("#search_box").fixDiv({ top: 0 });
    $('#search_btn').click(highlight);//点击search时，执行highlight函数；
    $('#searchstr').keydown(function (e) {
        var key = e.which;
        if (key == 13) highlight();
    })
    
    var i = 0;
    var sCurText;
    function highlight(){
        clearSelection();//先清空一下上次高亮显示的内容；
        
        var flag = 0;
        var bStart = true;
        
        
        $('#tip').text('');
        $('#tip').hide();
        var searchText = $('#searchstr').val();
        var _searchTop = $('#searchstr').offset().top+30;
        var _searchLeft = $('#searchstr').offset().left;
        if($.trim(searchText)=="" || $.trim(searchText)=='.'){
            //alert(123);
            showTips("请输入查找的物品",_searchTop,3,_searchLeft);
            return;
        }
            
            
        var searchText = $('#searchstr').val();//获取你输入的关键字；
        var regExp = new RegExp(searchText, 'g');//创建正则表达式，g表示全局的，如果不用g，则查找到第一个就不会继续向下查找了；
        var content = $("#content").text();
        if (!regExp.test(content)) {
            showTips("没有找到要查找的物品",_searchTop,3,_searchLeft);
            return;
        } else {
            if (sCurText != searchText) {
                i = 0;
                sCurText = searchText;
             }
         }
        
        $('p').each(function(){
            var html = $(this).html();
            var newHtml = html.replace(regExp, '<span class="highlight">'+searchText+'</span>');//将找到的关键字替换，加上highlight属性；

            $(this).html(newHtml);//更新；
            flag = 1;
        });
        
        if (flag == 1) {
            if ($(".highlight").size() > 1) {
                var _top = $(".highlight").eq(i).offset().top+$(".highlight").eq(i).height();
                var _tip = $(".highlight").eq(i).parent().find("strong").text();
                if(_tip=="") _tip = $(".highlight").eq(i).parent().parent().find("strong").text();
                var _left = $(".highlight").eq(i).offset().left;
                var _tipWidth = $("#tip").width();
                if (_left > $(document).width() - _tipWidth) {
                        _left = _left - _tipWidth;
                }
                $("#tip").html(_tip).show();
                $("#tip").offset({ top: _top, left: _left });
                $("#search_btn").val("下一个");
            }else{
                var _top = $(".highlight").offset().top+$(".highlight").height();
                var _tip = $(".highlight").parent().find("strong").text();
                var _left = $(".highlight").offset().left;
                $('#tip').show();
                $("#tip").html(_tip).offset({ top: _top, left: _left });
            }
            $("html, body").animate({ scrollTop: _top - 50 });
            i++;
            if (i > $(".highlight").size() - 1) {
                i = 0;
            }
        }
    }
    function clearSelection(){
        $('p').each(function(){
            //找到所有highlight属性的元素；
            $(this).find('.highlight').each(function(){
                $(this).replaceWith($(this).html());//将他们的属性去掉；
            });
        });
    }
    
    //mask
    var tipsDiv = '<div class="tipsClass"></div>'; 
    $( 'body' ).append( tipsDiv );
    function showTips( tips, height, time,left ){ 
        var windowWidth = document.documentElement.clientWidth; 
        $('.tipsClass').text(tips);
        $( 'div.tipsClass' ).css({ 
        'top' : height + 'px', 
        'left' :left + 'px', 
        'position' : 'absolute', 
        'padding' : '8px 6px', 
        'background': '#000000', 
        'font-size' : 14 + 'px', 
        'font-weight': 900,
        'margin' : '0 auto', 
        'text-align': 'center', 
        'width' : 'auto', 
        'color' : '#fff', 
        'border-radius':'2px', 
        'opacity' : '0.8' ,
        'box-shadow':'0px 0px 10px #000',
        '-moz-box-shadow':'0px 0px 10px #000',
        '-webkit-box-shadow':'0px 0px 10px #000'
        }).show(); 
        setTimeout( function(){$( 'div.tipsClass' ).fadeOut();}, ( time * 1000 ) ); 
    } 
})

